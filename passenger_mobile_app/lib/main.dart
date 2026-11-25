import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/transit_provider.dart';
import 'theme/movesync_theme.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'screens/explore_screen.dart';
import 'screens/tracking_screen.dart';
import 'screens/my_trips_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/authority_dashboard_screen.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => TransitProvider()),
      ],
      child: const SmartPassengerApp(),
    ),
  );
}

class SmartPassengerApp extends StatelessWidget {
  const SmartPassengerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MoveSync',
      debugShowCheckedModeBanner: false,
      theme: MoveSyncTheme.lightTheme,
      home: const RootNavigation(),
    );
  }
}

class RootNavigation extends StatefulWidget {
  const RootNavigation({super.key});

  @override
  State<RootNavigation> createState() => _RootNavigationState();
}

class _RootNavigationState extends State<RootNavigation> {
  int _currentIndex = 0;

  final List<Widget> _passengerScreens = const [
    HomeScreen(),
    ExploreScreen(),
    TrackingScreen(),
    MyTripsScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);

    if (!provider.isAuthenticated) {
      return const LoginScreen();
    }

    if (provider.isAuthority) {
      return const AuthorityDashboardScreen();
    }

    return Scaffold(
      body: _passengerScreens[_currentIndex],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (idx) => setState(() => _currentIndex = idx),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.explore_outlined), selectedIcon: Icon(Icons.explore), label: 'Explore'),
          NavigationDestination(icon: Icon(Icons.my_location_outlined), selectedIcon: Icon(Icons.my_location), label: 'Live'),
          NavigationDestination(icon: Icon(Icons.route_outlined), selectedIcon: Icon(Icons.route), label: 'My Trips'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}
