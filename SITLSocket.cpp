#include "SITLSocket.h"
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <thread>

// Platform-specific includes
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
    #define SOCKET_ERROR_CODE WSAGetLastError()
    #define CLOSE_SOCKET closesocket
#else
    #include <sys/socket.h>
    #include <sys/ioctl.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #include <fcntl.h>
    #include <netdb.h>
    #include <errno.h>
    #define SOCKET_ERROR_CODE errno
    #define CLOSE_SOCKET close
    #define INVALID_SOCKET -1
    #define SOCKET_ERROR -1
#endif

bool SITLSocket::socketsInitialized = false;

bool SITLSocket::initializeSockets()
{
#ifdef _WIN32
    if (socketsInitialized) return true;

    WSADATA wsaData;
    int result = WSAStartup(MAKEWORD(2, 2), &wsaData);
    if (result != 0) {
        fprintf(stderr, "SITL: WSAStartup failed: %d\n", result);
        return false;
    }
    socketsInitialized = true;
    return true;
#else
    socketsInitialized = true;
    return true;
#endif
}

void SITLSocket::cleanupSockets()
{
#ifdef _WIN32
    if (socketsInitialized) {
        WSACleanup();
        socketsInitialized = false;
    }
#endif
}

SITLSocket::SITLSocket()
    : socketFd(INVALID_SOCKET_VALUE), connected(false)
{
    initializeSockets();
}

SITLSocket::~SITLSocket()
{
    disconnect();
}

bool SITLSocket::connect(const char *host, int port)
{
    if (connected)
    {
        disconnect();
    }

    if (!initializeSockets())
    {
        return false;
    }

    // Create socket
    socketFd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (socketFd == INVALID_SOCKET_VALUE)
    {
        fprintf(stderr, "SITL: Failed to create socket: %d\n", SOCKET_ERROR_CODE);
        return false;
    }

    // Resolve hostname
    struct hostent *server = gethostbyname(host);
    if (server == nullptr)
    {
        fprintf(stderr, "SITL: Failed to resolve host '%s': %d\n", host, SOCKET_ERROR_CODE);
        CLOSE_SOCKET(socketFd);
        socketFd = INVALID_SOCKET_VALUE;
        return false;
    }

    // Setup address
    struct sockaddr_in serverAddr;
    memset(&serverAddr, 0, sizeof(serverAddr));
    serverAddr.sin_family = AF_INET;
    memcpy(&serverAddr.sin_addr.s_addr, server->h_addr, server->h_length);
    serverAddr.sin_port = htons(port);

    // --- NEW RETRY LOGIC ---
    printf("SITL: Attempting to connect to simulator at %s:%d...\n", host, port);

    while (true)
    {
        if (::connect(socketFd, (struct sockaddr *)&serverAddr, sizeof(serverAddr)) != SOCKET_ERROR)
        {
            // Success!
            break;
        }

        // Check if we failed for a reason other than "server not ready"
        // On Linux/Mac: ECONNREFUSED; On Windows: WSAECONNREFUSED
#ifdef _WIN32
        int err = WSAGetLastError();
        bool wouldRetry = (err == WSAECONNREFUSED);
#else
        int err = errno;
        bool wouldRetry = (err == ECONNREFUSED);
#endif

        if (!wouldRetry)
        {
            fprintf(stderr, "SITL: Fatal connection error: %d\n", err);
            CLOSE_SOCKET(socketFd);
            socketFd = INVALID_SOCKET_VALUE;
            return false;
        }

        // Wait 500ms before trying again to avoid pegging the CPU
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
    // --- END RETRY LOGIC ---

    // Set non-blocking mode for reads
#ifdef _WIN32
    u_long mode = 1; // Non-blocking
    if (ioctlsocket(socketFd, FIONBIO, &mode) != 0) {
        fprintf(stderr, "SITL: Failed to set non-blocking mode: %d\n", SOCKET_ERROR_CODE);
        CLOSE_SOCKET(socketFd);
        socketFd = INVALID_SOCKET_VALUE;
        return false;
    }
#else
    int flags = fcntl(socketFd, F_GETFL, 0);
    if (flags == -1) {
        fprintf(stderr, "SITL: Failed to get socket flags: %d\n", SOCKET_ERROR_CODE);
        CLOSE_SOCKET(socketFd);
        socketFd = INVALID_SOCKET_VALUE;
        return false;
    }
    if (fcntl(socketFd, F_SETFL, flags | O_NONBLOCK) == -1) {
        fprintf(stderr, "SITL: Failed to set non-blocking mode: %d\n", SOCKET_ERROR_CODE);
        CLOSE_SOCKET(socketFd);
        socketFd = INVALID_SOCKET_VALUE;
        return false;
    }
#endif

    connected = true;
    printf("SITL: Connected to %s:%d\n", host, port);
    return true;
}

void SITLSocket::disconnect()
{
    if (socketFd != INVALID_SOCKET_VALUE) {
        CLOSE_SOCKET(socketFd);
        socketFd = INVALID_SOCKET_VALUE;
    }
#ifndef PIO_UNIT_TESTING
    std::exit(0);
#endif
    connected = false;
}

bool SITLSocket::isConnected() const
{
    return connected;
}

int SITLSocket::write(const uint8_t* data, size_t len)
{
    if (!connected || socketFd == INVALID_SOCKET_VALUE) {
        return -1;
    }

    int totalSent = 0;
    while (totalSent < (int)len) {
        int sent = send(socketFd, (const char*)(data + totalSent), len - totalSent, 0);
        if (sent == SOCKET_ERROR) {
#ifdef _WIN32
            int err = WSAGetLastError();
            if (err == WSAEWOULDBLOCK) {
                // Would block - try again
                continue;
            }
#else
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                // Would block - try again
                continue;
            }
#endif
            fprintf(stderr, "SITL: Send error: %d\n", SOCKET_ERROR_CODE);
            disconnect();
            return -1;
        }
        totalSent += sent;
    }

    return totalSent;
}

int SITLSocket::read(uint8_t* buffer, size_t maxLen)
{
    if (!connected || socketFd == INVALID_SOCKET_VALUE) {
        return -1;
    }

    int received = recv(socketFd, (char*)buffer, maxLen, 0);

    if (received == SOCKET_ERROR) {
#ifdef _WIN32
        int err = WSAGetLastError();
        if (err == WSAEWOULDBLOCK) {
            return 0; // No data available
        }
#else
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return 0; // No data available
        }
#endif
        fprintf(stderr, "SITL: Receive error: %d\n", SOCKET_ERROR_CODE);
        disconnect();
        return -1;
    }

    if (received == 0) {
        // Connection closed by peer
        fprintf(stderr, "SITL: Connection closed by simulator\n");
        disconnect();
#ifndef PIO_UNIT_TESTING
        std::exit(0);
#endif
        return -1;
    }

    return received;
}

int SITLSocket::available()
{
    if (!connected || socketFd == INVALID_SOCKET_VALUE) {
        return 0;
    }

#ifdef _WIN32
    u_long bytesAvailable = 0;
    if (ioctlsocket(socketFd, FIONREAD, &bytesAvailable) == 0) {
        return (int)bytesAvailable;
    }
#else
    int bytesAvailable = 0;
    if (ioctl(socketFd, FIONREAD, &bytesAvailable) == 0) {
        return bytesAvailable;
    }
#endif

    return 0;
}
