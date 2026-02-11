#ifndef UNIT_TEST_SENSORS_H
#define UNIT_TEST_SENSORS_H

#include <Sensors/Baro/Barometer.h>
#include <Sensors/GPS/GPS.h>
#include <Sensors/Accel/Accel.h>
#include <Sensors/Gyro/Gyro.h>
#include <Sensors/Mag/Mag.h>
#include <Sensors/IMU/IMU6DoF.h>
#include <Sensors/IMU/IMU9DoF.h>
#include <Sensors/VoltageSensor/VoltageSensor.h>
#include <Sensors/Sensor.h>
#include <Math/Vector.h>
#include <Math/Quaternion.h>

using namespace astra;

class FakeBarometer : public Barometer
{
public:
    bool _healthy = true;
    double _altitude = 0.0;
    bool _shouldFailInit = false;

    FakeBarometer() : Barometer(), fakeAlt(0), fakeAltSet(false)
    {
        setName("FakeBarometer");
    }
    ~FakeBarometer() {}

    void reset()
    {
        initialized = false;
    }

    int read() override
    {
        pressure = fakeP;
        temp = fakeT;
        healthy = _healthy;  // Update health status when reading
        return 0;
    }

    // Override update() to prevent recalculation when altitude is set directly
    int update(double currentTime = -1) override
    {
        if (read() != 0)
            return -1;
        // Only calculate altitude from pressure if it wasn't set directly
        if (!fakeAltSet) {
            altitudeASL = calcAltitude(pressure);
        }
        // If altitude was set directly, altitudeASL is already correct
        return 0;
    }

    // Helper to set altitude directly
    void setAltitude(double altM)
    {
        fakeAlt = altM;
        _altitude = altM;
        fakeAltSet = true;
        // Calculate corresponding pressure for consistency
        fakeP = 101325.0 * pow(1.0 - altM / 44330.0, 5.255);
        fakeT = 15.0 - altM * 0.0065;
        pressure = fakeP;
        temp = fakeT;
        // Directly set the altitude in the base class
        altitudeASL = altM;
    }

    void set(double p, double t)
    {
        pressure = fakeP = p;
        temp = fakeT = t;
        fakeAltSet = false;
    }

    // Only override init() and read() like hardware sensors
    int init() override
    {
        if (_shouldFailInit) {
            return -1;
        }
        initialized = true;
        healthy = true;
        return 0;
    }

    bool isHealthy() const override { return _healthy; }

    double fakeP = 101325.0;  // Default to sea level
    double fakeT = 20.0;      // Default to 20C
    double fakeAlt = 0.0;
    int fakeAltSet = false;
};

class FakeGPS : public GPS
{
public:
    bool _healthy = true;
    bool _hasFix = false;
    bool _shouldFailInit = false;

    FakeGPS() : GPS()
    {
        setName("FakeGPS");
    }
    ~FakeGPS() {}

    void reset()
    {
        initialized = false;
    }

    int read() override {
        // Don't override fixQual or hasFix - they may have been set by test code
        // GPS::update() will handle the hasFix logic based on fixQual
        healthy = _healthy;  // Update health status when reading
        return 0;
    }
    void set(double lat, double lon, double alt)
    {
        position.x() = lat;
        position.y() = lon;
        position.z() = alt;
    }
    void setHeading(double h)
    {
        heading = h;
    }
    void setDateTime(int y, int m, int d, int h, int mm, int s)
    {
        year = y;
        month = m;
        day = d;
        hr = h;
        min = mm;
        sec = s;
        snprintf(tod, 12, "%02d:%02d:%02d", hr, min, sec); // size is really 9 but 12 ignores warnings about truncation. IRL it will never truncate
    }

    // Only override init() and read() like hardware sensors
    int init() override
    {
        if (_shouldFailInit) {
            return -1;
        }
        initialized = true;
        healthy = true;
        return 0;
    }

    void setHasFirstFix(int fix)
    {
        _hasFix = fix;
        hasFix = fix;
        if (fix)
            fixQual = 4;
        else
            fixQual = 0;
    }
    void setFixQual(int qual)
    {
        fixQual = qual;
    }
    // Don't override getHasFix() - let GPS::update() manage hasFix based on fixQual
    bool isHealthy() const override { return _healthy; }
};

class FakeAccel : public Accel
{
public:
    bool _healthy = true;
    Vector<3> _reading = Vector<3>(0, 0, -9.81);  // Match test expectations
    bool _shouldFailInit = false;

    FakeAccel() : Accel("FakeAccel")
    {
    }
    ~FakeAccel() {}

    // Only override init() and read() like hardware sensors
    int init() override
    {
        if (_shouldFailInit) {
            return -1;
        }
        acc = _reading;
        initialized = true;
        healthy = true;
        return 0;
    }

    int read() override
    {
        acc = _reading;
        healthy = _healthy;  // Update health status when reading
        return 0;
    }

    void set(Vector<3> accel)
    {
        _reading = accel;
        acc = accel;
    }

    bool isHealthy() const override { return _healthy; }

    void reset()
    {
        initialized = false;
    }
};

class FakeGyro : public Gyro
{
public:
    bool _healthy = true;
    Vector<3> _reading = Vector<3>(0, 0, 0);
    bool _shouldFailInit = false;

    FakeGyro() : Gyro("FakeGyro")
    {
    }
    ~FakeGyro() {}

    // Only override init() and read() like hardware sensors
    int init() override
    {
        if (_shouldFailInit) {
            return -1;
        }
        angVel = _reading;
        initialized = true;
        healthy = true;
        return 0;
    }

    int read() override
    {
        angVel = _reading;
        healthy = _healthy;  // Update health status when reading
        return 0;
    }

    void set(Vector<3> gyro)
    {
        _reading = gyro;
        angVel = gyro;
    }

    bool isHealthy() const override { return _healthy; }

    void reset()
    {
        initialized = false;
    }
};

class FakeMag : public Mag
{
public:
    bool _healthy = true;
    Vector<3> _reading = Vector<3>(0, 0, 0);  // Default to zero
    bool _shouldFailInit = false;

    FakeMag() : Mag("FakeMag")
    {
    }
    ~FakeMag() {}

    // Only override init() and read() like hardware sensors
    int init() override
    {
        if (_shouldFailInit) {
            return -1;
        }
        mag = _reading;
        initialized = true;
        healthy = true;
        return 0;
    }

    int read() override
    {
        mag = _reading;
        healthy = _healthy;  // Update health status when reading
        return 0;
    }

    void set(Vector<3> magField)
    {
        _reading = magField;
        mag = magField;
    }

    bool isHealthy() const override { return _healthy; }

    void reset()
    {
        initialized = false;
    }
};

class FakeIMU : public IMU6DoF
{
public:
    FakeIMU() : IMU6DoF("FakeIMU")
    {
    }
    ~FakeIMU() {}

    int init() override
    {
        acc = Vector<3>{0, 0, -9.81};
        angVel = Vector<3>{0, 0, 0};
        initialized = true;
        healthy = true;
        return 0;
    }

    int read() override
    {
        return 0;
    }

    void set(Vector<3> accel, Vector<3> gyro, Vector<3> mag = Vector<3>{0, 0, 0})
    {
        acc = accel;
        angVel = gyro;
        // Note: IMU6DoF doesn't have magnetometer, so mag is ignored
    }

    void reset()
    {
        initialized = false;
    }
};

class FakeIMU9DoF : public IMU9DoF
{
public:
    FakeIMU9DoF() : IMU9DoF("FakeIMU9DoF")
    {
    }
    ~FakeIMU9DoF() {}

    int init() override
    {
        acc = Vector<3>{0, 0, -9.81};
        angVel = Vector<3>{0, 0, 0};
        mag = Vector<3>{20, 0, 0};
        initialized = true;
        healthy = true;
        return 0;
    }

    int read() override
    {
        return 0;
    }

    void set(Vector<3> accel, Vector<3> gyro, Vector<3> magField)
    {
        acc = accel;
        angVel = gyro;
        mag = magField;
    }

    void reset()
    {
        initialized = false;
    }
};

class FakeSensor : public Sensor
{
public:
    FakeSensor(const char *name = "FakeSensor") : Sensor(name) {}
    ~FakeSensor() {}

    int init() override
    {
        initialized = true;
        healthy = true;
        return 0;
    }

    int read() override
    {
        return 0;
    }
};

// Failing sensor for testing error handling
class FakeFailingAccel : public Accel {
public:
    FakeFailingAccel() : Accel("FailingAccel") {}
    // Only override init() and read() like hardware sensors
    int init() override { return -1; }  // Fail
    int read() override {
        acc = Vector<3>(0, 0, 0);
        return 0;
    }
};

class MockVoltageSensor : public VoltageSensor
{
public:
    bool initCalled = false;
    bool readCalled = false;
    int storedPin;

    MockVoltageSensor(int pin, const char *name = "MockVoltage")
        : VoltageSensor(pin, name), storedPin(pin) {}
    MockVoltageSensor(int pin, int r1, int r2, const char *name = "MockVoltage", double refVoltage = 3.3)
        : VoltageSensor(pin, r1, r2, name, refVoltage), storedPin(pin) {}

    int init() override
    {
        initCalled = true;
        initialized = true;
        healthy = true;
        return 0;
    }

    int read() override
    {
        readCalled = true;
        // Call the parent class read() which will use analogRead()
        return VoltageSensor::read();
    }

    // Helper to set the mock ADC value for this sensor's pin
    void setMockRawValue(int value)
    {
        setMockAnalogRead(storedPin, value);
    }
};

#endif // UNIT_TEST_SENSORS_H
