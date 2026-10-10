#pragma once

#include "CoreMinimal.h"

namespace WindowAstronomy
{
struct FSolarPosition
{
    double ElevationRadians = 0, AzimuthRadians = 0, SolarMinutes = 0;
};

// Existing NOAA fractional-year model, now shared with the rendering checks.
// https://gml.noaa.gov/grad/solcalc/solareqns.PDF
inline FSolarPosition SolarPosition(const FDateTime& LocalTime, double Latitude, double Longitude, double OffsetSeconds)
{
    const double Hour = LocalTime.GetTimeOfDay().GetTotalHours();
    const double Days = FDateTime::IsLeapYear(LocalTime.GetYear()) ? 366. : 365.;
    const double G = 2 * UE_DOUBLE_PI / Days * (LocalTime.GetDayOfYear() - 1 + (Hour - 12) / 24.);
    const double Decl = .006918 - .399912 * FMath::Cos(G) + .070257 * FMath::Sin(G)
        - .006758 * FMath::Cos(2 * G) + .000907 * FMath::Sin(2 * G)
        - .002697 * FMath::Cos(3 * G) + .00148 * FMath::Sin(3 * G);
    const double Equation = 229.18 * (.000075 + .001868 * FMath::Cos(G) - .032077 * FMath::Sin(G)
        - .014615 * FMath::Cos(2 * G) - .040849 * FMath::Sin(2 * G));
    FSolarPosition Result;
    Result.SolarMinutes = Hour * 60 + Equation + 4 * Longitude - OffsetSeconds / 60.;
    const double H = FMath::DegreesToRadians(Result.SolarMinutes / 4 - 180);
    const double Lat = FMath::DegreesToRadians(Latitude);
    Result.ElevationRadians = FMath::Asin(FMath::Clamp(FMath::Sin(Lat) * FMath::Sin(Decl)
        + FMath::Cos(Lat) * FMath::Cos(Decl) * FMath::Cos(H), -1., 1.));
    Result.AzimuthRadians = FMath::Atan2(FMath::Sin(H), FMath::Cos(H) * FMath::Sin(Lat)
        - FMath::Tan(Decl) * FMath::Cos(Lat)) + UE_DOUBLE_PI;
    return Result;
}

struct FMoonPosition
{
    double ElevationDegrees = 0, AzimuthRadians = 0, IlluminatedFraction = 0, DistanceEarthRadii = 0;
    FVector Direction = FVector::UpVector; // +X east, -Y north, +Z up
};

// Schlyter's low-order orbit with principal lunar perturbations and observer parallax.
// https://stjarnhimlen.se/comp/tutorial.html#7
// ponytail: spherical Earth; no refraction/eclipses. Use a full ephemeris if sub-degree accuracy is needed.
inline FMoonPosition MoonPosition(const FDateTime& LocalTime, double Latitude, double Longitude, double OffsetSeconds)
{
    const double Rad = UE_DOUBLE_PI / 180.;
    const auto Sin = [Rad](double X) { return FMath::Sin(X * Rad); };
    const auto Cos = [Rad](double X) { return FMath::Cos(X * Rad); };
    const auto Rev = [](double X) { return X - 360. * FMath::Floor(X / 360.); };
    const auto Eccentric = [Rad](double MeanDegrees, double Ecc)
    {
        const double M = MeanDegrees * Rad;
        double E = M + Ecc * FMath::Sin(M) * (1. + Ecc * FMath::Cos(M));
        for (int I = 0; I < 5; ++I) E -= (E - Ecc * FMath::Sin(E) - M) / (1. - Ecc * FMath::Cos(E));
        return E;
    };
    const double JD = (LocalTime - FTimespan::FromSeconds(OffsetSeconds)).GetJulianDay();
    const double D = JD - 2451543.5;
    const double Obliquity = 23.4393 - 3.563e-7 * D;
    const double Ms = Rev(356.0470 + .9856002585 * D), Ws = Rev(282.9404 + 4.70935e-5 * D);
    const double SunE = .016709 - 1.151e-9 * D, Es = Eccentric(Ms, SunE);
    const double SunLon = FMath::Atan2(FMath::Sqrt(1. - SunE * SunE) * FMath::Sin(Es), FMath::Cos(Es) - SunE) / Rad + Ws;
    const double N = Rev(125.1228 - .0529538083 * D), W = Rev(318.0634 + .1643573223 * D);
    const double M = Rev(115.3654 + 13.0649929509 * D), E = Eccentric(M, .0549);
    const double X = 60.2666 * (FMath::Cos(E) - .0549), Y = 60.2666 * FMath::Sqrt(1. - .0549 * .0549) * FMath::Sin(E);
    double R = FMath::Sqrt(X * X + Y * Y);
    const double V = FMath::Atan2(Y, X) / Rad;
    const double Xe = R * (Cos(N) * Cos(V + W) - Sin(N) * Sin(V + W) * Cos(5.1454));
    const double Ye = R * (Sin(N) * Cos(V + W) + Cos(N) * Sin(V + W) * Cos(5.1454));
    const double Ze = R * Sin(V + W) * Sin(5.1454);
    double Lon = FMath::Atan2(Ye, Xe) / Rad, Lat = FMath::Atan2(Ze, FMath::Sqrt(Xe * Xe + Ye * Ye)) / Rad;
    const double Lm = N + W + M, Elongation = Lm - (Ws + Ms), F = Lm - N;
    Lon += -1.274 * Sin(M - 2 * Elongation) + .658 * Sin(2 * Elongation) - .186 * Sin(Ms)
        - .059 * Sin(2 * M - 2 * Elongation) - .057 * Sin(M - 2 * Elongation + Ms)
        + .053 * Sin(M + 2 * Elongation) + .046 * Sin(2 * Elongation - Ms) + .041 * Sin(M - Ms)
        - .035 * Sin(Elongation) - .031 * Sin(M + Ms) - .015 * Sin(2 * F - 2 * Elongation)
        + .011 * Sin(M - 4 * Elongation);
    Lat += -.173 * Sin(F - 2 * Elongation) - .055 * Sin(M - F - 2 * Elongation)
        - .046 * Sin(M + F - 2 * Elongation) + .033 * Sin(F + 2 * Elongation) + .017 * Sin(2 * M + F);
    R += -.58 * Cos(M - 2 * Elongation) - .46 * Cos(2 * Elongation);
    const auto Equatorial = [&](double L, double B)
    {
        const double Ex = Cos(L) * Cos(B), Ey = Sin(L) * Cos(B), Ez = Sin(B);
        return FVector(Ex, Ey * Cos(Obliquity) - Ez * Sin(Obliquity), Ey * Sin(Obliquity) + Ez * Cos(Obliquity));
    };
    const FVector Moon = Equatorial(Lon, Lat), Solar = Equatorial(SunLon, 0.);
    const double LST = Rev(280.46061837 + 360.98564736629 * (JD - 2451545.) + Longitude);
    const FVector Up(Cos(Latitude) * Cos(LST), Cos(Latitude) * Sin(LST), Sin(Latitude));
    const FVector East(-Sin(LST), Cos(LST), 0.);
    const FVector North(-Sin(Latitude) * Cos(LST), -Sin(Latitude) * Sin(LST), Cos(Latitude));
    const FVector Topocentric = (Moon * R - Up).GetSafeNormal();
    const double Eastward = FVector::DotProduct(Topocentric, East), Northward = FVector::DotProduct(Topocentric, North);
    const double Alt = FMath::Asin(FMath::Clamp(FVector::DotProduct(Topocentric, Up), -1., 1.));
    FMoonPosition Result;
    Result.ElevationDegrees = Alt / Rad;
    Result.AzimuthRadians = FMath::Atan2(Eastward, Northward);
    Result.IlluminatedFraction = FMath::Clamp((1. - FVector::DotProduct(Moon, Solar)) * .5, 0., 1.);
    Result.DistanceEarthRadii = R;
    Result.Direction = FVector(Eastward, -Northward, FMath::Sin(Alt)).GetSafeNormal();
    return Result;
}
}
