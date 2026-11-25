import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/transit_models.dart';
import '../services/api_service.dart';
import '../services/websocket_service.dart';

class TransitProvider with ChangeNotifier {
  final ApiService api = ApiService();
  final WebSocketService ws = WebSocketService();

  UserProfile? _currentUser;
  bool _isAuthenticated = false;

  List<TransitRoute> _routes = [];
  List<BusState> _buses = [];
  List<CrowdingAlert> _alerts = [];
  TransitRoute? _selectedRoute;
  BusState? _selectedBus;
  BusLocation? _selectedBusLocation;
  List<StopForecast> _currentForecasts = [];

  bool _isLoading = false;
  String? _errorMessage;

  // Authority-only state
  List<DispatchRecommendation> _pendingDispatches = [];
  List<RouteDemandItem> _routeDemand = [];
  FuelSummary? _fuelSummary;
  PassengerCountingSummary? _cvSummary;
  Map<String, BusLocation> _allBusLocations = {};
  Map<String, dynamic> _schedulesByRoute = {};
  List<CrowdingAlert> _alertHistory = [];

  // Passenger Nearby Stops & Journey state
  double? _passengerLat;
  double? _passengerLon;
  String _locationStatus = 'Location not requested yet';
  bool _locationPermissionDenied = false;
  List<NearbyStop> _nearbyStops = [];
  List<NearbyStop> _stopSearchResults = [];
  String _sourceStopQuery = '';
  String _destinationStopQuery = '';

  // Getters
  UserProfile? get currentUser => _currentUser;
  bool get isAuthenticated => _isAuthenticated;
  bool get isAuthority =>
      _currentUser != null &&
      (_currentUser!.role.toLowerCase() == 'authority' ||
          _currentUser!.role.toLowerCase() == 'administrator');
  List<TransitRoute> get routes => _routes;
  List<BusState> get buses => _buses;
  List<CrowdingAlert> get alerts => _alerts;
  TransitRoute? get selectedRoute => _selectedRoute;
  BusState? get selectedBus => _selectedBus;
  BusLocation? get selectedBusLocation => _selectedBusLocation;
  List<StopForecast> get currentForecasts => _currentForecasts;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;

  List<DispatchRecommendation> get pendingDispatches => _pendingDispatches;
  List<RouteDemandItem> get routeDemand => _routeDemand;
  FuelSummary? get fuelSummary => _fuelSummary;
  PassengerCountingSummary? get cvSummary => _cvSummary;
  Map<String, BusLocation> get allBusLocations => _allBusLocations;
  Map<String, dynamic> get schedulesByRoute => _schedulesByRoute;
  List<CrowdingAlert> get alertHistory => _alertHistory;

  double? get passengerLat => _passengerLat;
  double? get passengerLon => _passengerLon;
  String get locationStatus => _locationStatus;
  bool get locationPermissionDenied => _locationPermissionDenied;
  List<NearbyStop> get nearbyStops => _nearbyStops;
  List<NearbyStop> get stopSearchResults => _stopSearchResults;
  String get sourceStopQuery => _sourceStopQuery;
  String get destinationStopQuery => _destinationStopQuery;

  // Authentication
  Future<bool> login(String email, String password) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();
    try {
      final res = await api.login(email, password);
      _currentUser = UserProfile.fromJson(res['user']);
      _isAuthenticated = true;
      _isLoading = false;
      ws.connect(WebSocketService.defaultWsUrl, api.authToken);
      if (isAuthority) {
        ws.subscribeTopic('authority_alerts');
      }
      notifyListeners();
      await refreshData();
      return true;
    } catch (e) {
      _isLoading = false;
      _errorMessage = e.toString().replaceAll('Exception: ', '');
      notifyListeners();
      return false;
    }
  }

  Future<bool> register(String email, String password, String name) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();
    try {
      final res = await api.register(email, password, name);
      if (res['status'] == 'success') {
        _isLoading = false;
        notifyListeners();
        return await login(email, password);
      } else {
        _errorMessage = res['message'] ?? 'Registration failed';
        _isLoading = false;
        notifyListeners();
        return false;
      }
    } catch (e) {
      _isLoading = false;
      _errorMessage = e.toString().replaceAll('Exception: ', '');
      notifyListeners();
      return false;
    }
  }

  void logout() {
    _currentUser = null;
    _isAuthenticated = false;
    _pendingDispatches = [];
    _routeDemand = [];
    _fuelSummary = null;
    _cvSummary = null;
    _allBusLocations = {};
    _schedulesByRoute = {};
    api.setToken(null);
    ws.disconnect();
    notifyListeners();
  }

  // Network Fetching
  Future<void> refreshData() async {
    _isLoading = true;
    notifyListeners();
    try {
      _routes = await api.fetchRoutes();
      _buses = await api.fetchBuses();
      _alerts = await api.fetchActiveAlerts();
      if (isAuthority) {
        _pendingDispatches = await api.fetchPendingDispatches();
        _routeDemand = await api.fetchRouteDemand();
        _fuelSummary = await api.fetchFuelSummary();
        _cvSummary = await api.fetchPassengerCountingSummary();
        _alertHistory = await api.fetchAlertHistory();
        for (final r in _routes) {
          _schedulesByRoute[r.routeId] = await api.fetchSchedule(r.routeId);
        }
        for (final b in _buses.where((x) => x.status == 'IN_SERVICE')) {
          try {
            _allBusLocations[b.busId] = await api.fetchBusLocation(b.busId);
          } catch (_) {}
        }
      } else {
        // Load default searchable stops so Explore & Nearby have real surveyed stops ready
        _stopSearchResults = await api.searchStops('');
      }
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _isLoading = false;
      _errorMessage = 'Failed to load transit data';
      notifyListeners();
    }
  }

  static const MethodChannel _locationChannel = MethodChannel('com.movesync/location');

  Future<void> detectPassengerLocation() async {
    _locationStatus = 'Detecting your location...';
    _locationPermissionDenied = false;
    notifyListeners();
    try {
      final result = await _locationChannel.invokeMapMethod<String, dynamic>('getCurrentLocation');
      if (result != null && result['lat'] != null && result['lon'] != null) {
        final lat = (result['lat'] as num).toDouble();
        final lon = (result['lon'] as num).toDouble();
        _passengerLat = lat;
        _passengerLon = lon;
        _locationStatus = 'GPS active (${lat.toStringAsFixed(4)}, ${lon.toStringAsFixed(4)})';
        _nearbyStops = await api.fetchNearbyStops(lat, lon, radiusKm: 15.0);
      } else {
        _locationStatus = result?['error']?.toString() ?? 'Location unavailable. Use manual stop search.';
        _locationPermissionDenied = true;
      }
      notifyListeners();
    } catch (e) {
      _locationStatus = 'Location permission denied or unavailable. Use manual stop search.';
      _locationPermissionDenied = true;
      notifyListeners();
    }
  }

  Future<void> searchStops(String query) async {
    _stopSearchResults = await api.searchStops(query);
    notifyListeners();
  }

  void setJourneyStops(String source, String destination) {
    _sourceStopQuery = source;
    _destinationStopQuery = destination;
    notifyListeners();
  }

  Future<Map<String, dynamic>> acknowledgeAlert(String alertId) async {
    final res = await api.acknowledgeAlert(alertId);
    if (res['ok'] == true) {
      await refreshData();
    }
    return res;
  }

  Future<Map<String, dynamic>> resolveAlert(String alertId) async {
    final res = await api.resolveAlert(alertId);
    if (res['ok'] == true) {
      await refreshData();
    }
    return res;
  }

  Future<Map<String, dynamic>> submitCountingSession({
    required String busId,
    required String routeId,
    required String sessionId,
    required int boardingCount,
    required int alightingCount,
  }) async {
    final res = await api.submitCountingSession(
      busId: busId,
      routeId: routeId,
      sessionId: sessionId,
      boardingCount: boardingCount,
      alightingCount: alightingCount,
    );
    if (res['ok'] == true) {
      await refreshData();
    }
    return res;
  }

  Future<bool> decideDispatch(String recommendationId, String decision) async {
    final ok = await api.decideDispatch(recommendationId, decision);
    if (ok) {
      await refreshData();
    }
    return ok;
  }

  void selectRoute(TransitRoute route) {
    _selectedRoute = route;
    notifyListeners();
  }

  Future<void> selectBus(BusState bus) async {
    _selectedBus = bus;
    notifyListeners();
    try {
      _selectedBusLocation = await api.fetchBusLocation(bus.busId);
      if (bus.lastStopId != null) {
        _currentForecasts = await api.fetchPredictions(bus.busId, bus.lastStopId!);
      }
      notifyListeners();
    } catch (e) {
      debugPrint('Error fetching bus details: $e');
    }
  }

  // Alternative Less-Crowded Buses Algorithm
  List<BusState> getAlternativeBuses(String routeId, String currentBusId) {
    return _buses
        .where((b) => b.currentRouteId == routeId && b.busId != currentBusId)
        .toList()
      ..sort((a, b) => a.currentOccupancy.compareTo(b.currentOccupancy));
  }
}

