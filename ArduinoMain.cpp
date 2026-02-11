/**
 * Arduino-style main() entry point for native SITL builds
 *
 * This file provides a standard main() function that calls setup() once
 * and loop() repeatedly, mimicking Arduino behavior on native platforms.
 *
 * Only compiled when NOT running unit tests (when PIO_UNIT_TESTING is not defined)
 */

#if !defined(PIO_UNIT_TESTING) && !defined(UNITY_BEGIN)

#include "Arduino.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>

// Forward declarations for setup() and loop() from user code
extern void setup();
extern void loop();

// Signal handler for crashes
void crash_handler(int sig) {
    const char* signal_name = "UNKNOWN";
    switch(sig) {
        case SIGSEGV: signal_name = "SIGSEGV (Segmentation Fault)"; break;
        case SIGABRT: signal_name = "SIGABRT (Abort)"; break;
        case SIGFPE: signal_name = "SIGFPE (Floating Point Exception)"; break;
        case SIGILL: signal_name = "SIGILL (Illegal Instruction)"; break;
    }

    fprintf(stderr, "\n\n");
    fprintf(stderr, "========================================\n");
    fprintf(stderr, "CRASH DETECTED!\n");
    fprintf(stderr, "Signal: %s (%d)\n", signal_name, sig);
    fprintf(stderr, "========================================\n");
    fprintf(stderr, "The program crashed. Possible causes:\n");
    fprintf(stderr, "  - Null pointer dereference\n");
    fprintf(stderr, "  - Buffer overflow\n");
    fprintf(stderr, "  - Stack overflow\n");
    fprintf(stderr, "  - Division by zero\n");
    fprintf(stderr, "  - Invalid memory access\n");
    fprintf(stderr, "========================================\n");
    fflush(stderr);

    // Exit with error code
    exit(sig);
}

int main(int argc, char** argv) {
    // Install crash handlers
    signal(SIGSEGV, crash_handler);
    signal(SIGABRT, crash_handler);
    signal(SIGFPE, crash_handler);
    signal(SIGILL, crash_handler);

    printf("Signal handlers installed\n");
    fflush(stdout);

    // Call setup once
    setup();

    // Call loop repeatedly
    while (true) {
        loop();
    }

    return 0;
}

#endif // !PIO_UNIT_TESTING && !UNITY_BEGIN
