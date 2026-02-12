#include "Arduino.h"
#include "SITLSocket.h"
#include <iostream>
#include <map>

static void spin_wait_us(uint64_t us)
{
    const auto start_point = std::chrono::steady_clock::now();
    while (std::chrono::duration_cast<std::chrono::microseconds>(
               std::chrono::steady_clock::now() - start_point)
               .count() < static_cast<long long>(us)) {
    }
}

const uint64_t start = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
const uint64_t startMicros = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
uint64_t fakeMillis = 0;
bool useFakeMillis = false;

uint64_t millis()
{
    if (useFakeMillis)
    {
        return fakeMillis;
    }
    return (std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch()).count() - start);
}

uint64_t micros()
{
    if (useFakeMillis)
    {
        return fakeMillis * 1000;
    }
    return (std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count() - startMicros);
}

void setMillis(uint64_t ms)
{
    fakeMillis = ms;
    useFakeMillis = true;
}

void resetMillis()
{
    fakeMillis = 0;
    useFakeMillis = false;
}

void delay(unsigned long ms)
{
    spin_wait_us(static_cast<uint64_t>(ms) * 1000ULL);
}

void delay(int ms)
{
    if (ms <= 0) {
        return;
    }
    spin_wait_us(static_cast<uint64_t>(ms) * 1000ULL);
}

void delayMicroseconds(unsigned int us)
{
    spin_wait_us(us);
}

void yield()
{
    // Cooperative no-op for native mocks.
}

void pinMode(int pin, int mode)
{
    // Mock - does nothing
}

void digitalWrite(int pin, int value)
{

    int color;
    switch (pin)
    {
    case 13:
        color = 36;
        break;
    case 33:
        color = 33;
        break;
    case 32:
        color = 95;
        break;
    default:
        color = 0;
        break;
    }
    printf("\x1B[%dm%.3f - %d to \x1B[%dm%s\x1B[0m\n", color, millis() / 1000.0, pin, value == LOW ? 91 : 92, value == LOW ? "LOW" : "HIGH");
}

int digitalRead(int pin)
{
    // Mock - always return LOW
    return LOW;
}

// Map to store mock analog read values
static std::map<int, int> mockAnalogValues;

int analogRead(int pin)
{
    // Check if there's a mocked value for this pin
    if (mockAnalogValues.find(pin) != mockAnalogValues.end()) {
        return mockAnalogValues[pin];
    }
    // Mock - return a default analog value (mid-range)
    return 512;
}

void setMockAnalogRead(int pin, int value)
{
    mockAnalogValues[pin] = value;
}

void clearMockAnalogReads()
{
    mockAnalogValues.clear();
}

Stream::~Stream()
{
    disconnectSITL();
}

void Stream::begin(int baud) {}
void Stream::end()
{
    disconnectSITL();
}

void Stream::clearBuffer()
{
    cursor = 0;
    fakeBuffer[0] = '\0';
    inputCursor = 0;
    inputLength = 0;
    inputBuffer[0] = '\0';
}

void Stream::pollSITLInput()
{
    if (!sitlSocket || !sitlSocket->isConnected()) {
        return;
    }

    // If the buffer has been fully consumed, reset it before polling for new data.
    // This prevents the buffer from growing indefinitely.
    if (inputCursor >= inputLength) {
        inputCursor = 0;
        inputLength = 0;
    }

    // Check if there's room in the input buffer
    int roomAvailable = sizeof(inputBuffer) - inputLength;
    if (roomAvailable <= 0) {
        return; // Buffer full
    }

    // Read available data from SITL socket
    uint8_t tempBuffer[256];
    int bytesRead = sitlSocket->read(tempBuffer, sizeof(tempBuffer) < roomAvailable ? sizeof(tempBuffer) : roomAvailable);

    if (bytesRead > 0) {
        // Append to input buffer
        memcpy(inputBuffer + inputLength, tempBuffer, bytesRead);
        inputLength += bytesRead;
        inputBuffer[inputLength] = '\0';
    }
}

bool Stream::available()
{
    // Poll for new SITL data if connected
    pollSITLInput();

    return inputCursor < inputLength;
}

int Stream::read()
{
    // Poll for new SITL data if connected
    pollSITLInput();

    if (inputCursor >= inputLength)
    {
        return -1;
    }
    return (uint8_t)inputBuffer[inputCursor++];
}

void Stream::simulateInput(const char *data)
{
    if (!data)
        return;

    inputLength = strlen(data);
    if (inputLength >= sizeof(inputBuffer))
    {
        inputLength = sizeof(inputBuffer) - 1;
    }

    memcpy(inputBuffer, data, inputLength);
    inputBuffer[inputLength] = '\0';
    inputCursor = 0;
}

int Stream::peek()
{
    pollSITLInput();
    if (inputCursor >= inputLength)
    {
        return -1;
    }
    return (uint8_t)inputBuffer[inputCursor];
}

int Stream::readBytesUntil(char terminator, char *buffer, size_t length)
{
    if (length < 1) return 0;
    size_t index = 0;
    while (index < length) {
        int c = read();
        if (c < 0) break;
        if (c == terminator) break;
        buffer[index++] = (char)c;
    }
    return index;
}

size_t Stream::readBytes(char *buffer, size_t length)
{
    size_t count = 0;
    while (count < length) {
        int c = read();
        if (c < 0) break;
        buffer[count++] = (char)c;
    }
    return count;
}

size_t Stream::readBytes(uint8_t *buffer, size_t length)
{
    return readBytes((char *)buffer, length);
}

size_t Stream::write(uint8_t b)
{
    // Write to fake buffer for debugging/logging
    if (cursor < sizeof(fakeBuffer) - 1) {
        fakeBuffer[cursor++] = b;
        fakeBuffer[cursor] = '\0';
    }
    // std::cout << b;


    // If SITL is connected, send to external simulator
    if (sitlSocket && sitlSocket->isConnected()) {
        sitlSocket->write(&b, 1);
    }

    return 1;
}

bool Stream::connectSITL(const char* host, int port)
{
    if (!sitlSocket) {
        sitlSocket = new SITLSocket();
    }

    if (sitlSocket->isConnected()) {
        sitlSocket->disconnect();
    }

    return sitlSocket->connect(host, port);
}

void Stream::disconnectSITL()
{
    if (sitlSocket) {
        sitlSocket->disconnect();
        delete sitlSocket;
        sitlSocket = nullptr;
    }
}

bool Stream::isSITLConnected() const
{
    return sitlSocket && sitlSocket->isConnected();
}

HardwareSerial Serial;
HardwareSerial Serial1;
HardwareSerial Serial2;
HardwareSerial Serial3;
CrashReportClass CrashReport;
