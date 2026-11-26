cmake_minimum_required(VERSION 3.16)
project(pi_tools C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra)

add_executable(hello   src/hello.c)
add_executable(gpioinfo_mini src/gpioinfo_mini.c)
add_executable(spi_loopback  src/spi_loopback.c)

# Deploy: cmake --build build --target deploy  (uses an SSH host alias, default "testbed")
set(PI_HOST testbed CACHE STRING "SSH host alias of the target")
add_custom_target(deploy
    COMMAND scp $<TARGET_FILE:hello> $<TARGET_FILE:gpioinfo_mini> ${PI_HOST}:~/
    DEPENDS hello gpioinfo_mini
    COMMENT "Copying binaries to ${PI_HOST}")
