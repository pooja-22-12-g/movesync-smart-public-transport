import 'package:flutter/material.dart';

class MoveSyncTheme {
  static const Color navy = Color(0xFF102B46);
  static const Color teal = Color(0xFF16A6A0);
  static const Color white = Color(0xFFFFFFFF);
  static const Color lightGrey = Color(0xFFF4F7FA);
  static const Color amber = Color(0xFFE9A23B);
  static const Color red = Color(0xFFD93025);
  static const Color green = Color(0xFF1E8E3E);
  static const Color lightBlue = Color(0xFFE8F1F8);

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: lightGrey,
      primaryColor: navy,
      colorScheme: const ColorScheme.light(
        primary: navy,
        secondary: teal,
        surface: white,
        error: red,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: navy,
        foregroundColor: white,
        elevation: 0,
        centerTitle: false,
      ),
      cardTheme: CardThemeData(
        color: white,
        elevation: 1,
        shadowColor: Colors.black12,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: navy,
          foregroundColor: white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          elevation: 0,
        ),
      ),
    );
  }

  static Color statusColor(String status) {
    switch (status.toUpperCase()) {
      case 'CRITICAL':
        return red;
      case 'WARNING':
        return amber;
      default:
        return green;
    }
  }

  /// Plain-language crowding label for Passengers (no technical/ML jargon)
  static String passengerCrowdLabel(int occupancy, int capacity) {
    final pct = capacity > 0 ? (occupancy / capacity) * 100.0 : 0.0;
    if (pct >= 95) return 'Full';
    if (pct >= 80) return 'Crowded';
    if (pct >= 55) return 'Moderately Crowded';
    return 'Seats Available';
  }
}
