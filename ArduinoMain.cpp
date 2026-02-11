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

// Forward declarations for setup() and loop() from user code
extern void setup();
extern void loop();

int main(int argc, char** argv) {
    // Call setup once
    setup();

    // Call loop repeatedly
    while (true) {
        loop();
    }

    return 0;
}

#endif // !PIO_UNIT_TESTING && !UNITY_BEGIN
