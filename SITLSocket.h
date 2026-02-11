#ifndef SITL_SOCKET_H
#define SITL_SOCKET_H

#include <cstdint>
#include <cstddef>

/**
 * SITLSocket: Cross-platform TCP socket wrapper for Software-In-The-Loop simulation
 *
 * Provides a simple interface for connecting to an external simulator via TCP.
 * The flight software acts as a TCP client, connecting to a simulator server.
 *
 * Thread-safe buffered I/O with non-blocking reads.
 */
class SITLSocket
{
public:
    SITLSocket();
    ~SITLSocket();

    /**
     * Connect to SITL simulator server
     * @param host Hostname or IP address (e.g., "localhost" or "127.0.0.1")
     * @param port Port number (e.g., 5555)
     * @return true if connection successful
     */
    bool connect(const char* host, int port);

    /**
     * Disconnect from simulator
     */
    void disconnect();

    /**
     * Check if connected to simulator
     */
    bool isConnected() const;

    /**
     * Write data to simulator (blocking)
     * @param data Pointer to data buffer
     * @param len Number of bytes to write
     * @return Number of bytes actually written, -1 on error
     */
    int write(const uint8_t* data, size_t len);

    /**
     * Read available data from simulator (non-blocking)
     * @param buffer Pointer to buffer to fill
     * @param maxLen Maximum bytes to read
     * @return Number of bytes read, 0 if none available, -1 on error
     */
    int read(uint8_t* buffer, size_t maxLen);

    /**
     * Check if data is available to read
     * @return Number of bytes available (may be approximate)
     */
    int available();

private:
#ifdef _WIN32
    typedef unsigned long long SOCKET_TYPE;
    static const SOCKET_TYPE INVALID_SOCKET_VALUE = ~0ULL;
#else
    typedef int SOCKET_TYPE;
    static const SOCKET_TYPE INVALID_SOCKET_VALUE = -1;
#endif

    SOCKET_TYPE socketFd;  // Socket file descriptor
    bool connected;

    // Platform-specific initialization (Winsock on Windows)
    static bool initializeSockets();
    static void cleanupSockets();
    static bool socketsInitialized;
};

#endif // SITL_SOCKET_H
