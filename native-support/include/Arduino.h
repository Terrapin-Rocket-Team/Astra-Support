#ifndef ARDUINO_H
#define ARDUINO_H

#ifdef __cplusplus
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cmath>
#include <chrono>
#else
#include <stdint.h>
#include <stdio.h>
#include <math.h>
#endif

#include <string.h>
#include <stdarg.h>
#include "Wire.h"
#include "Print.h"
#define SS 10 // random ass numbers lol

#define HIGH 1
#define LOW 0

#define INPUT 1
#define OUTPUT 0
#define INPUT_PULLUP 2
#define INPUT_PULLDOWN 3

// Platform ADC configuration for testing
#define PLATFORM_ADC_BITS 10
#define PLATFORM_DEFAULT_REF_VOLTAGE 3.3

#define A0 0

#define LED_BUILTIN 13
#define BUILTIN_SDCARD 254

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Arduino print format constants
#define DEC 10
#define HEX 16
#define OCT 8
#define BIN 2

// SPI bit order
#define LSBFIRST 0
#define MSBFIRST 1
typedef uint8_t BitOrder;

// F() macro for flash strings (just return the string on native)
#define F(string_literal) (string_literal)

// PROGMEM macros - on native, just store in regular memory
#define PROGMEM
#define PGM_P const char *
#define PSTR(s) (s)
#define pgm_read_byte(addr) (*(const uint8_t *)(addr))
#define pgm_read_word(addr) (*(const uint16_t *)(addr))
#define pgm_read_dword(addr) (*(const uint32_t *)(addr))
#define pgm_read_float(addr) (*(const float *)(addr))
#define pgm_read_ptr(addr) (*(const void **)(addr))
#define memcpy_P(dest, src, num) memcpy((dest), (src), (num))
#define strcpy_P(dest, src) strcpy((dest), (src))
#define strcmp_P(a, b) strcmp((a), (b))
#define strlen_P(s) strlen((s))
#define strncpy_P(dest, src, num) strncpy((dest), (src), (num))
#define strncmp_P(a, b, n) strncmp((a), (b), (n))

#ifdef __cplusplus
// Flash string helper type
class __FlashStringHelper;
typedef const __FlashStringHelper *FlashStringHelper;

// Arduino boolean and byte types
typedef bool boolean;
typedef uint8_t byte;

// Arduino helper functions
template<typename T>
T constrain(T x, T low, T high) {
    if (x < low) return low;
    if (x > high) return high;
    return x;
}

template<typename T, typename U, typename V>
T map(T x, U in_min, U in_max, V out_min, V out_max) {
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

template<typename T>
T min(T a, T b) {
    return (a < b) ? a : b;
}

template<typename T>
T max(T a, T b) {
    return (a > b) ? a : b;
}
#endif // __cplusplus

uint64_t millis();
uint64_t micros();

void setMillis(uint64_t ms);

void resetMillis();

void delay(unsigned long ms);

void delayMicroseconds(unsigned int us);

void yield();

void digitalWrite(int pin, int value);

int digitalRead(int pin);

void pinMode(int pin, int mode);

int analogRead(int pin);

// Mock helpers for testing
void setMockAnalogRead(int pin, int value);
void clearMockAnalogReads();

#ifdef __cplusplus

// Forward declaration for SITL support
class SITLSocket;

// Arduino String class
#include <string>
class String {
private:
    std::string str;
public:
    String() : str("") {}
    String(const char* s) : str(s ? s : "") {}
    String(const std::string& s) : str(s) {}
    String(int n) : str(std::to_string(n)) {}
    String(unsigned int n) : str(std::to_string(n)) {}
    String(long n) : str(std::to_string(n)) {}
    String(unsigned long n) : str(std::to_string(n)) {}
    String(float f) : str(std::to_string(f)) {}
    String(double d) : str(std::to_string(d)) {}

    const char* c_str() const { return str.c_str(); }
    size_t length() const { return str.length(); }
    bool startsWith(const char* prefix) const {
        return str.find(prefix) == 0;
    }
    bool startsWith(const String& prefix) const {
        return str.find(prefix.str) == 0;
    }
    int indexOf(char c) const {
        size_t pos = str.find(c);
        return (pos == std::string::npos) ? -1 : (int)pos;
    }
    String substring(int start) const {
        return String(str.substr(start));
    }
    String substring(int start, int end) const {
        return String(str.substr(start, end - start));
    }
    void trim() {
        size_t first = str.find_first_not_of(" \t\r\n");
        if (std::string::npos == first) {
            str = "";
        } else {
            size_t last = str.find_last_not_of(" \t\r\n");
            str = str.substr(first, (last - first + 1));
        }
    }
    long toInt() const {
        try { return std::stol(str); } catch (...) { return 0; }
    }
    float toFloat() const {
        try { return std::stof(str); } catch (...) { return 0.0f; }
    }
    double toDouble() const {
        try { return std::stod(str); } catch (...) { return 0.0; }
    }
    
    String& operator+=(char c) {
        str += c;
        return *this;
    }
    String& operator+=(const char* s) {
        str += (s ? s : "");
        return *this;
    }
    
    operator const char*() const { return str.c_str(); }
    bool operator==(const String& other) const { return str == other.str; }
    bool operator==(const char* other) const { return str == (other ? other : ""); }
};

class Stream : public Print
{
public:
    Stream() = default;
    ~Stream();
    void begin(int baud = 9600);
    void end();
    void clearBuffer();
    virtual bool available();  // Mock - no data available
    virtual int peek();
    virtual int read();  // Mock read - returns -1 (no data)
    int readBytesUntil(char i, char *buf, size_t s);
    size_t readBytes(char *buf, size_t len);
    size_t readBytes(uint8_t *buf, size_t len);
    size_t write(uint8_t b) override;
    size_t write(const uint8_t *buf, size_t len) {  // Add buffer write
        size_t written = 0;
        for (size_t i = 0; i < len; i++) {
            written += write(buf[i]);
        }
        return written;
    }
    
    String readString() {
        String ret = "";
        int c = read();
        while (c >= 0) {
            ret += (char)c;
            c = read();
        }
        return ret;
    }

    String readStringUntil(char terminator) {
        String ret = "";
        unsigned long startTime = millis();
        const unsigned long timeout = 1000; // 1 second timeout

        while (millis() - startTime < timeout) {
            int c = read();
            if (c < 0) {
                // No data available - yield and try again
                delayMicroseconds(100);
                continue;
            }
            if (c == terminator) {
                // Found terminator - success
                break;
            }
            ret += (char)c;
        }
        return ret;
    }

    operator bool() { return true; }

    // For simulating incoming data in tests
    void simulateInput(const char *data);

    // SITL (Software-In-The-Loop) mode - connect to external simulator
    bool connectSITL(const char* host, int port);
    void disconnectSITL();
    bool isSITLConnected() const;

    char fakeBuffer[1000];
    int cursor = 0;
    // Input buffer for read operations
    char inputBuffer[1000];
    int inputCursor = 0;
    int inputLength = 0;

private:
    SITLSocket* sitlSocket = nullptr;  // TCP connection to external simulator
    void pollSITLInput();  // Poll for incoming data from simulator
};



class SerialClass : public Stream
{
public:
};
class HardwareSerial : public SerialClass
{
public:
};

extern HardwareSerial Serial;
extern HardwareSerial Serial1;
extern HardwareSerial Serial2;
extern HardwareSerial Serial3;

class CrashReportClass
{
public:
    explicit CrashReportClass() {}
    operator bool() const { return false; }
};
extern CrashReportClass CrashReport;

#endif // __cplusplus

#endif // ARDUINO_H
