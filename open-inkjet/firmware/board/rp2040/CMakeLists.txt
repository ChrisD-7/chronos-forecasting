# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
# Build: export PICO_SDK_PATH=/path/to/pico-sdk (2.x, submodules initialised); cmake -B build -G Ninja . && cmake --build build
cmake_minimum_required(VERSION 3.13)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(openinkjet C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

add_executable(openinkjet_fw
    main.c oi_board.c
    ../../core/oi_app.c ../../core/oi_job.c ../../core/oi_proto.c ../../core/oi_sched.c
    ../../core/oi_motion.c ../../core/oi_maint.c ../../core/oi_head_matrix.c)
target_include_directories(openinkjet_fw PRIVATE ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(openinkjet_fw pico_stdlib pico_multicore pico_sync hardware_spi hardware_pwm hardware_gpio hardware_clocks hardware_sync)
pico_enable_stdio_usb(openinkjet_fw 1)
pico_enable_stdio_uart(openinkjet_fw 0)
target_compile_options(openinkjet_fw PRIVATE -Wall -Wextra -Werror)
pico_add_extra_outputs(openinkjet_fw)
