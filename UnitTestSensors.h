#ifndef UNIT_TEST_SENSORS_H
#define UNIT_TEST_SENSORS_H

#include <Sensors/Baro/Barometer.h>
#include <Sensors/GPS/GPS.h>
#include <Sensors/Accel/Accel.h>
#include <Sensors/Gyro/Gyro.h>
#include <Sensors/IMU/IMU6DoF.h>
#include <Math/Vector.h>
#include <Math/Quaternion.h>

using namespace astra;

class FakeBarometer : public Barometer
{
public:
    FakeBarometer() : Barometer(), fakeAlt(0), fakeAltSet(false)
    {
        initialized = true;
        setName("FakeBarometer");
    }
    ~FakeBarometer() {}

    bool read() override
    {
        pressure = fakeP;
        temp = fakeT;
        return true;
    }

    // Override update() to prevent recalculation when altitude is set directly
    bool update() override
    {
        if (!read())
            return false;
        // Only calculate altitude from pressure if it wasn't set directly
        if (!fakeAltSet) {
            altitudeASL = calcAltitude(pressure);
        }
        // If altitude was set directly, altitudeASL is already correct
        return true;
    }

    // Helper to set altitude directly
    void setAltitude(double altM)
    {
        fakeAlt = altM;
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

    bool init() override
    {
        return initialized;
    }

    double fakeP = 101325.0;  // Default to sea level
    double fakeT = 20.0;      // Default to 20C
    double fakeAlt = 0.0;
    bool fakeAltSet = false;
};

class FakeGPS : public GPS
{
public:
    FakeGPS() : GPS()
    {
        initialized = true;
        setName("FakeGPS");
    }
    ~FakeGPS() {}

    bool read() override {
        return true;
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

    bool init() override
    {
        return initialized;
    }

    void setHasFirstFix(bool fix)
    {
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
};

class FakeAccel : public Accel
{
public:
    FakeAccel() : Accel("FakeAccel")
    {
        initialized = true;
    }
    ~FakeAccel() {}

    bool read() override
    {
        return true;
    }

    void set(Vector<3> accel)
    {
        acc = accel;
    }

    bool init() override
    {
        acc = Vector<3>{0, 0, -9.81};
        return initialized;
    }
};

class FakeGyro : public Gyro
{
public:
    FakeGyro() : Gyro("FakeGyro")
    {
        initialized = true;
    }
    ~FakeGyro() {}

    bool read() override
    {
        return true;
    }

    void set(Vector<3> gyro)
    {
        angVel = gyro;
    }

    bool init() override
    {
        angVel = Vector<3>{0, 0, 0};
        return true;
    }

    bool isInitialized() const override
    {
        return true;
    }
};

class FakeIMU : public IMU6DoF
{
public:
    FakeIMU() : IMU6DoF("FakeIMU")
    {
        initialized = true;
    }
    ~FakeIMU() {}

    bool init() override
    {
        acc = Vector<3>{0, 0, -9.81};
        angVel = Vector<3>{0, 0, 0};
        initialized = true;
        return true;
    }

    bool read() override
    {
        return true;
    }

    void set(Vector<3> accel, Vector<3> gyro, Vector<3> mag = Vector<3>{0, 0, 0})
    {
        acc = accel;
        angVel = gyro;
        // Note: IMU6DoF doesn't have magnetometer, so mag is ignored
    }

    bool isInitialized() const override
    {
        return initialized;
    }
};

#endif // UNIT_TEST_SENSORS_H
