/*
 * belt_counter: conveyor-belt object counter for a Raspberry Pi with a UVC camera.
 *
 * Captures YUYV 320x240 through V4L2, finds objects that differ from the dominant
 * surface (a white sheet of paper), tracks them and counts how many cross a
 * vertical line, separately for leftward and rightward crossings.
 *
 * Output (stdout, to the PC): one message per frame
 *   F seq ts_ms w h count_left count_right nobj proc_us cpu_x10 line_pct len yref\n
 *   O id x0 y0 x1 y1 flag\n            (nobj lines, flag 0 none, 1 counted left, 2 counted right)
 *   <len bytes of YUYV>                (len is 0 on frames that are not sent for display)
 * Commands (stdin, from the PC), one per line:
 *   RESET | LINE pct | THY n | THC n | MINA n | MAXA n | DISP n
 * The program stops when stdin is closed, so it never outlives the SSH session.
 *
 * Self-test without a camera:  belt_counter --selftest
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

#define W 320
#define H 240
#define CELL 4
#define GW (W / CELL)
#define GH (H / CELL)
#define NCELL (GW * GH)
#define MAXT 16
#define MAXO 16
#define FRAME_BYTES (W * H * 2)

typedef struct {
    int id;
    float cx, cy;
    int x0, y0, x1, y1;
    int missed;
    int side; /* -1 left of the line, +1 right of it */
    int flag; /* last crossing: 1 left, 2 right */
} Track;

typedef struct {
    int id, x0, y0, x1, y1, flag;
} Obj;

typedef struct {
    int line_pct, line_cell, hyst;
    int thr_y, thr_c, min_area, max_area;
    Track t[MAXT];
    int nt, next_id;
    int count_left, count_right;
    Obj objs[MAXO];
    int nobj;
    int y_ref;
    uint8_t gy[NCELL], gu[NCELL], gv[NCELL], mask[NCELL];
} Counter;

static void counter_set_line(Counter *c, int pct)
{
    if (pct < 5) pct = 5;
    if (pct > 95) pct = 95;
    c->line_pct = pct;
    c->line_cell = pct * GW / 100;
}

static void counter_init(Counter *c)
{
    memset(c, 0, sizeof *c);
    c->hyst = 2;
    c->thr_y = 35;
    c->thr_c = 30;
    c->min_area = 6;
    c->max_area = 900;
    c->next_id = 1;
    counter_set_line(c, 25);
}

static void build_grid(Counter *c, const uint8_t *f)
{
    for (int gy = 0; gy < GH; gy++)
        for (int gx = 0; gx < GW; gx++) {
            int sy = 0, su = 0, sv = 0;
            for (int r = 0; r < CELL; r++) {
                const uint8_t *p = f + ((gy * CELL + r) * W + gx * CELL) * 2;
                for (int k = 0; k < CELL / 2; k++, p += 4) {
                    sy += p[0] + p[2];
                    su += p[1];
                    sv += p[3];
                }
            }
            int i = gy * GW + gx;
            c->gy[i] = sy / (CELL * CELL);
            c->gu[i] = su / (CELL * CELL / 2);
            c->gv[i] = sv / (CELL * CELL / 2);
        }
}

/* The dominant brightness (the sheet of paper) is the busiest +-10 window of the Y histogram. */
static void find_reference(Counter *c, int *yref, int *uref, int *vref)
{
    int hist[256] = {0};
    for (int i = 0; i < NCELL; i++) hist[c->gy[i]]++;
    int best = 0, bestsum = -1;
    for (int v = 0; v < 256; v++) {
        int s = 0;
        for (int d = -10; d <= 10; d++)
            if (v + d >= 0 && v + d < 256) s += hist[v + d];
        if (s > bestsum) { bestsum = s; best = v; }
    }
    long sy = 0, n = 0;
    for (int i = 0; i < NCELL; i++)
        if (abs(c->gy[i] - best) <= 10) { sy += c->gy[i]; n++; }
    *yref = n ? (int)(sy / n) : best;
    long su = 0, sv = 0;
    n = 0;
    for (int i = 0; i < NCELL; i++)
        if (abs(c->gy[i] - *yref) <= 12) { su += c->gu[i]; sv += c->gv[i]; n++; }
    *uref = n ? (int)(su / n) : 128;
    *vref = n ? (int)(sv / n) : 128;
}

typedef struct {
    int area, x0, y0, x1, y1;
    long sx, sy;
    int taken;
} Blob;

static int find_blobs(Counter *c, Blob *out, int maxb)
{
    static int stack[NCELL];
    int nb = 0;
    for (int s = 0; s < NCELL; s++) {
        if (c->mask[s] != 1) continue;
        Blob b = {0, GW, GH, 0, 0, 0, 0, 0};
        int sp = 0;
        stack[sp++] = s;
        c->mask[s] = 2;
        while (sp) {
            int i = stack[--sp];
            int x = i % GW, y = i / GW;
            b.area++;
            b.sx += x;
            b.sy += y;
            if (x < b.x0) b.x0 = x;
            if (x > b.x1) b.x1 = x;
            if (y < b.y0) b.y0 = y;
            if (y > b.y1) b.y1 = y;
            if (x > 0 && c->mask[i - 1] == 1) { c->mask[i - 1] = 2; stack[sp++] = i - 1; }
            if (x < GW - 1 && c->mask[i + 1] == 1) { c->mask[i + 1] = 2; stack[sp++] = i + 1; }
            if (y > 0 && c->mask[i - GW] == 1) { c->mask[i - GW] = 2; stack[sp++] = i - GW; }
            if (y < GH - 1 && c->mask[i + GW] == 1) { c->mask[i + GW] = 2; stack[sp++] = i + GW; }
        }
        if (b.area >= c->min_area && b.area <= c->max_area && nb < maxb) out[nb++] = b;
    }
    return nb;
}

static void counter_process(Counter *c, const uint8_t *frame)
{
    build_grid(c, frame);
    int yref, uref, vref;
    find_reference(c, &yref, &uref, &vref);
    c->y_ref = yref;
    for (int i = 0; i < NCELL; i++) {
        int dy = abs(c->gy[i] - yref);
        int dc = abs(c->gu[i] - uref) + abs(c->gv[i] - vref);
        c->mask[i] = (dy > c->thr_y || dc > c->thr_c) ? 1 : 0;
    }
    Blob blobs[MAXO * 2];
    int nb = find_blobs(c, blobs, MAXO * 2);

    int matched[MAXT] = {0};
    for (int bi = 0; bi < nb; bi++) {
        Blob *b = &blobs[bi];
        float cx = (float)b->sx / b->area, cy = (float)b->sy / b->area;
        int bt = -1;
        float bd = 14.0f * 14.0f;
        for (int ti = 0; ti < c->nt; ti++) {
            if (matched[ti]) continue;
            float dx = c->t[ti].cx - cx, dy = c->t[ti].cy - cy;
            float d = dx * dx + dy * dy;
            if (d < bd) { bd = d; bt = ti; }
        }
        if (bt < 0) {
            if (c->nt >= MAXT) continue;
            bt = c->nt++;
            Track *t = &c->t[bt];
            memset(t, 0, sizeof *t);
            t->id = c->next_id++;
            t->side = cx < c->line_cell ? -1 : 1;
            matched[bt] = 1;
        }
        matched[bt] = 1;
        Track *t = &c->t[bt];
        t->cx = cx;
        t->cy = cy;
        t->x0 = b->x0; t->y0 = b->y0; t->x1 = b->x1; t->y1 = b->y1;
        t->missed = 0;
        int ns = t->side;
        if (cx < c->line_cell - c->hyst) ns = -1;
        else if (cx > c->line_cell + c->hyst) ns = 1;
        if (ns != t->side) {
            if (t->side == 1 && ns == -1) { c->count_left++; t->flag = 1; }
            else { c->count_right++; t->flag = 2; }
            t->side = ns;
        }
    }
    /* age tracks that were not seen; drop the stale ones */
    int w = 0;
    for (int ti = 0; ti < c->nt; ti++) {
        if (!matched[ti]) c->t[ti].missed++;
        if (c->t[ti].missed <= 6) c->t[w++] = c->t[ti];
    }
    c->nt = w;
    c->nobj = 0;
    for (int ti = 0; ti < c->nt && c->nobj < MAXO; ti++) {
        if (c->t[ti].missed) continue;
        Track *t = &c->t[ti];
        c->objs[c->nobj++] = (Obj){t->id, t->x0 * CELL, t->y0 * CELL, (t->x1 + 1) * CELL, (t->y1 + 1) * CELL, t->flag};
    }
}

/* ------------------------------------------------------------------ self-test */

static uint32_t rng_state = 12345;
static int rnd(int n)
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return (int)((rng_state >> 16) % (unsigned)n);
}

static void synth_bg(uint8_t *f, int yv)
{
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            uint8_t *p = f + (y * W + x) * 2;
            int v = yv + rnd(7) - 3;
            p[0] = (uint8_t)v;
            p[1] = (uint8_t)(128 + rnd(3) - 1);
        }
}

static void synth_rect(uint8_t *f, int rx, int ry, int rw, int rh, int Y, int U, int V)
{
    for (int y = ry; y < ry + rh; y++)
        for (int x = rx; x < rx + rw; x++) {
            if (x < 0 || x >= W || y < 0 || y >= H) continue;
            uint8_t *p = f + (y * W + x) * 2;
            p[0] = (uint8_t)Y;
            p[1] = (uint8_t)((x & 1) ? V : U);
        }
}

static int check(const char *name, int ok)
{
    printf("  %-58s %s\n", name, ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}

static int run_selftest(void)
{
    static uint8_t f[FRAME_BYTES];
    Counter c;
    int fails = 0;
    printf("belt_counter self-test (synthetic frames, no camera)\n");

    counter_init(&c);
    for (int i = 0; i < 100; i++) { synth_bg(f, 235); counter_process(&c, f); }
    fails += check("noise only: no objects, count 0", c.count_left == 0 && c.count_right == 0);

    counter_init(&c);
    for (int i = 0; i < 110; i++) {
        synth_bg(f, 235);
        synth_rect(f, 330 - i * 4, 50, 24, 16, 70, 100, 190);       /* red-ish eraser   */
        if (i > 20) synth_rect(f, 330 - (i - 20) * 4, 110, 20, 20, 60, 190, 100); /* blue */
        if (i > 40) synth_rect(f, 330 - (i - 40) * 4, 170, 28, 12, 190, 60, 150); /* yellow */
        counter_process(&c, f);
    }
    printf("    (left=%d right=%d)\n", c.count_left, c.count_right);
    fails += check("3 objects moved left across the line: left=3, right=0", c.count_left == 3 && c.count_right == 0);

    counter_init(&c);
    for (int i = 0; i < 100; i++) {
        synth_bg(f, 235);
        synth_rect(f, -30 + i * 4, 100, 24, 16, 70, 100, 190);
        counter_process(&c, f);
    }
    fails += check("1 object moved right across the line: right=1, left=0", c.count_left == 0 && c.count_right == 1);

    counter_init(&c);
    for (int i = 0; i < 110; i++) {
        synth_bg(f, 235 - i * 60 / 110);                              /* exposure drifts darker */
        synth_rect(f, 330 - i * 4, 80, 24, 16, 50, 100, 190);
        counter_process(&c, f);
    }
    fails += check("brightness drifts 235 -> 175 while 1 object passes: left=1", c.count_left == 1 && c.count_right == 0);

    counter_init(&c);
    for (int i = 0; i < 110; i++) {
        synth_bg(f, 235);
        synth_rect(f, 330 - i * 4, 0, 120, H, 30, 128, 128);          /* big dark band: paper edge */
        counter_process(&c, f);
    }
    fails += check("paper edge (large dark band) is ignored: count 0", c.count_left == 0 && c.count_right == 0);

    counter_init(&c);
    for (int i = 0; i < 110; i++) {
        synth_bg(f, 235);
        synth_rect(f, 330 - i * 4, 100, 24, 16, 242, 128, 128);       /* white on white */
        counter_process(&c, f);
    }
    printf("  %-58s left=%d (known limit)\n", "white object on white paper (info, not a pass/fail test)", c.count_left);

    printf(fails ? "SELF-TEST FAIL (%d)\n" : "SELF-TEST PASS\n", fails);
    return fails ? 1 : 0;
}

/* ------------------------------------------------------------------ camera */

static volatile sig_atomic_t stop_flag;
static void on_signal(int s) { (void)s; stop_flag = 1; }

static int xioctl(int fd, unsigned long req, void *arg)
{
    int r;
    do r = ioctl(fd, req, arg);
    while (r == -1 && errno == EINTR);
    return r;
}

static long long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static long long now_us(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

static void handle_command(Counter *c, char *line, int *disp)
{
    int n;
    if (!strncmp(line, "RESET", 5)) { c->count_left = c->count_right = 0; c->nt = 0; }
    else if (sscanf(line, "LINE %d", &n) == 1) counter_set_line(c, n);
    else if (sscanf(line, "THY %d", &n) == 1 && n > 0) c->thr_y = n;
    else if (sscanf(line, "THC %d", &n) == 1 && n > 0) c->thr_c = n;
    else if (sscanf(line, "MINA %d", &n) == 1 && n > 0) c->min_area = n;
    else if (sscanf(line, "MAXA %d", &n) == 1 && n > 0) c->max_area = n;
    else if (sscanf(line, "DISP %d", &n) == 1 && n > 0) *disp = n;
}

int main(int argc, char **argv)
{
    const char *dev = "/dev/video0";
    int disp = 1, ignore_eof = 0;
    long max_frames = 0;
    Counter c;
    counter_init(&c);
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--selftest")) return run_selftest();
        else if (!strcmp(argv[i], "--dev") && i + 1 < argc) dev = argv[++i];
        else if (!strcmp(argv[i], "--disp") && i + 1 < argc) disp = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--line") && i + 1 < argc) counter_set_line(&c, atoi(argv[++i]));
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) max_frames = atol(argv[++i]);
        else if (!strcmp(argv[i], "--ignore-eof")) ignore_eof = 1;
        else { fprintf(stderr, "usage: %s [--selftest] [--dev D] [--disp N] [--line PCT] [--frames N] [--ignore-eof]\n", argv[0]); return 2; }
    }
    if (disp < 1) disp = 1;

    signal(SIGPIPE, SIG_IGN);
    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);

    int fd = open(dev, O_RDWR);
    if (fd < 0) { perror("open camera"); return 1; }

    struct v4l2_format fmt;
    memset(&fmt, 0, sizeof fmt);
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = W;
    fmt.fmt.pix.height = H;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV;
    fmt.fmt.pix.field = V4L2_FIELD_NONE;
    if (xioctl(fd, VIDIOC_S_FMT, &fmt) < 0) { perror("S_FMT"); return 1; }
    if (fmt.fmt.pix.width != W || fmt.fmt.pix.height != H || fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_YUYV) {
        fprintf(stderr, "camera did not accept YUYV %dx%d\n", W, H);
        return 1;
    }
    struct v4l2_streamparm parm;
    memset(&parm, 0, sizeof parm);
    parm.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    parm.parm.capture.timeperframe.numerator = 1;
    parm.parm.capture.timeperframe.denominator = 30;
    xioctl(fd, VIDIOC_S_PARM, &parm);
    /* keep 30 fps in dim light: this is the "exposure_dynamic_framerate" control */
    struct v4l2_control ctl = {V4L2_CID_EXPOSURE_AUTO_PRIORITY, 0};
    xioctl(fd, VIDIOC_S_CTRL, &ctl);

    struct v4l2_requestbuffers req;
    memset(&req, 0, sizeof req);
    req.count = 4;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (xioctl(fd, VIDIOC_REQBUFS, &req) < 0) { perror("REQBUFS"); return 1; }
    void *bufp[8];
    size_t bufl[8];
    for (unsigned i = 0; i < req.count && i < 8; i++) {
        struct v4l2_buffer b;
        memset(&b, 0, sizeof b);
        b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        b.memory = V4L2_MEMORY_MMAP;
        b.index = i;
        if (xioctl(fd, VIDIOC_QUERYBUF, &b) < 0) { perror("QUERYBUF"); return 1; }
        bufl[i] = b.length;
        bufp[i] = mmap(NULL, b.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, b.m.offset);
        if (bufp[i] == MAP_FAILED) { perror("mmap"); return 1; }
        if (xioctl(fd, VIDIOC_QBUF, &b) < 0) { perror("QBUF"); return 1; }
    }
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (xioctl(fd, VIDIOC_STREAMON, &type) < 0) { perror("STREAMON"); return 1; }

    static char outbuf[1 << 17];
    setvbuf(stdout, outbuf, _IOFBF, sizeof outbuf);
    char cmd[256];
    size_t cmdlen = 0;
    long seq = 0;
    long long cpu_t0 = 0, wall_t0 = now_us();
    int cpu_x10 = 0;
    struct rusage ru0;
    getrusage(RUSAGE_SELF, &ru0);
    cpu_t0 = (long long)(ru0.ru_utime.tv_sec + ru0.ru_stime.tv_sec) * 1000000 + ru0.ru_utime.tv_usec + ru0.ru_stime.tv_usec;
    int rc = 0;

    int stdin_open = 1;
    while (!stop_flag && (!max_frames || seq < max_frames)) {
        struct pollfd pf[2] = {{fd, POLLIN, 0}, {stdin_open ? 0 : -1, POLLIN, 0}};
        int pr = poll(pf, 2, 2000);
        if (pr < 0) { if (errno == EINTR) continue; break; }
        if (pf[1].revents & (POLLIN | POLLHUP)) {
            char tmp[128];
            ssize_t n = read(0, tmp, sizeof tmp);
            if (n == 0 && !ignore_eof) break;
            for (ssize_t i = 0; i < n; i++) {
                if (tmp[i] == '\n' || cmdlen >= sizeof cmd - 1) {
                    cmd[cmdlen] = 0;
                    handle_command(&c, cmd, &disp);
                    cmdlen = 0;
                } else {
                    cmd[cmdlen++] = tmp[i];
                }
            }
            if (n == 0) stdin_open = 0;
        }
        if (!(pf[0].revents & POLLIN)) continue;
        struct v4l2_buffer b;
        memset(&b, 0, sizeof b);
        b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        b.memory = V4L2_MEMORY_MMAP;
        if (xioctl(fd, VIDIOC_DQBUF, &b) < 0) { if (errno == EAGAIN) continue; perror("DQBUF"); rc = 1; break; }
        const uint8_t *data = bufp[b.index];
        long long t0 = now_us();
        counter_process(&c, data);
        long long proc_us = now_us() - t0;
        seq++;
        if (seq % 30 == 0) {
            struct rusage ru;
            getrusage(RUSAGE_SELF, &ru);
            long long cpu = (long long)(ru.ru_utime.tv_sec + ru.ru_stime.tv_sec) * 1000000 + ru.ru_utime.tv_usec + ru.ru_stime.tv_usec;
            long long wall = now_us();
            cpu_x10 = (int)((cpu - cpu_t0) * 1000 / (wall - wall_t0 > 0 ? wall - wall_t0 : 1));
            cpu_t0 = cpu;
            wall_t0 = wall;
        }
        int send_img = (seq % disp) == 0;
        int ok = printf("F %ld %lld %d %d %d %d %d %lld %d %d %d %d\n", seq, now_ms(), W, H, c.count_left, c.count_right,
                        c.nobj, proc_us, cpu_x10, c.line_pct, send_img ? FRAME_BYTES : 0, c.y_ref) > 0;
        for (int i = 0; i < c.nobj; i++)
            printf("O %d %d %d %d %d %d\n", c.objs[i].id, c.objs[i].x0, c.objs[i].y0, c.objs[i].x1, c.objs[i].y1, c.objs[i].flag);
        if (send_img) ok = ok && fwrite(data, 1, FRAME_BYTES, stdout) == FRAME_BYTES;
        ok = ok && fflush(stdout) == 0;
        xioctl(fd, VIDIOC_QBUF, &b);
        if (!ok) break;
    }
    xioctl(fd, VIDIOC_STREAMOFF, &type);
    for (unsigned i = 0; i < req.count && i < 8; i++) munmap(bufp[i], bufl[i]);
    close(fd);
    return rc;
}
