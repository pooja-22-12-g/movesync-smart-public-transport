import 'dart:convert';
import 'dart:async';
import 'package:http/http.dart' as http;
import '../models/transit_models.dart';

class ApiService {
  // Configured via --dart-define=API_BASE_URL=https://... for cloud deployment;
  // defaults to local development URL when --dart-define is omitted.
  static const String defaultBaseUrl = 'http://10.0.2.2:8000';
  static const String lanBaseUrl = 'http://192.168.1.7:8000';
  static const String configuredBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: lanBaseUrl);

  String baseUrl = configuredBaseUrl;
  String? authToken;

  void setBaseUrl(String url) {
    baseUrl = url;
  }

  void setToken(String? token) {
    authToken = token;
  }

  Map<String, String> get _headers {
    final headers = {'Content-Type': 'application/json'};
    if (authToken != null) {
      headers['Authorization'] = 'Bearer $authToken';
    }
    return headers;
  }

  // 1. Authentication
  Future<Map<String, dynamic>> register(String email, String password, String name) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/auth/register'),
      headers: _headers,
      body: jsonEncode({
        'email': email,
        'password': password,
        'display_name': name,
        'requested_role': 'passenger',
      }),
    );
    return jsonDecode(response.body);
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/auth/login'),
      headers: _headers,
      body: jsonEncode({
        'email': email,
        'password': password,
      }),
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      authToken = data['access_token'];
      return data;
    } else {
      throw Exception(jsonDecode(response.body)['detail'] ?? 'Login failed');
    }
  }

  // 2. Routes & Stops
  Future<List<TransitRoute>> fetchRoutes() async {
    final response = await http.get(Uri.parse('$baseUrl/api/routes'), headers: _headers);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['routes'] as List;
      return list.map((r) => TransitRoute.fromJson(r)).toList();
    }
    return [];
  }

  Future<TransitRoute?> fetchRouteDetails(String routeId) async {
    final response = await http.get(Uri.parse('$baseUrl/api/routes/$routeId'), headers: _headers);
    if (response.statusCode == 200) {
      return TransitRoute.fromJson(jsonDecode(response.body));
    }
    return null;
  }

  // 3. Buses & Fleet Occupancy
  Future<List<BusState>> fetchBuses({String? routeId}) async {
    final url = routeId != null ? '$baseUrl/api/buses?route_id=$routeId' : '$baseUrl/api/buses';
    final response = await http.get(Uri.parse(url), headers: _headers);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['buses'] as List;
      return list.map((b) => BusState.fromJson(b)).toList();
    }
    return [];
  }

  Future<BusState?> fetchBus(String busId) async {
    final response = await http.get(Uri.parse('$baseUrl/api/buses/$busId'), headers: _headers);
    if (response.statusCode == 200) {
      return BusState.fromJson(jsonDecode(response.body));
    }
    return null;
  }

  // 4. Live Spatial Location
  Future<BusLocation> fetchBusLocation(String busId) async {
    final response = await http.get(Uri.parse('$baseUrl/api/bus-locations/$busId'), headers: _headers);
    if (response.statusCode == 200) {
      return BusLocation.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to load bus location');
  }

  // 5. Multi-Stop Occupancy Forecasts (Module 5 integration)
  Future<List<StopForecast>> fetchPredictions(String busId, String stopId) async {
    final response = await http.get(Uri.parse('$baseUrl/api/predictions/$busId/$stopId'), headers: _headers);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      if (data['lookahead_forecasts'] != null) {
        final forecasts = data['lookahead_forecasts'] as List;
        return forecasts.map((f) => StopForecast.fromJson(f)).toList();
      }
    }
    return [];
  }

  // 6. Active Crowding Alerts
  Future<List<CrowdingAlert>> fetchActiveAlerts({String? routeId}) async {
    final url = routeId != null ? '$baseUrl/api/alerts/active?route_id=$routeId' : '$baseUrl/api/alerts/active';
    final response = await http.get(Uri.parse(url), headers: _headers);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['alerts'] as List;
      return list.map((a) => CrowdingAlert.fromJson(a)).toList();
    }
    return [];
  }

  // 7. Nearby Bus Stops & Stop Search
  Future<List<NearbyStop>> fetchNearbyStops(double lat, double lon, {double radiusKm = 5.0}) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/stops/nearby?lat=$lat&lon=$lon&radius_km=$radiusKm'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['stops'] as List? ?? [];
      return list.map((s) => NearbyStop.fromJson(s)).toList();
    }
    return [];
  }

  Future<List<NearbyStop>> searchStops(String query) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/stops/search?q=${Uri.encodeComponent(query)}'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['stops'] as List? ?? [];
      return list.map((s) => NearbyStop.fromJson(s)).toList();
    }
    return [];
  }

  // 8. Authority Operations APIs
  Future<List<CrowdingAlert>> fetchAlertHistory() async {
    final response = await http.get(Uri.parse('$baseUrl/api/alerts/history'), headers: _headers);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['alerts'] as List? ?? [];
      return list.map((a) => CrowdingAlert.fromJson(a)).toList();
    }
    return [];
  }

  Future<Map<String, dynamic>> acknowledgeAlert(String alertId) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/alerts/$alertId/acknowledge'),
      headers: _headers,
    );
    return {'ok': response.statusCode == 200, ...jsonDecode(response.body)};
  }

  Future<Map<String, dynamic>> resolveAlert(String alertId) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/alerts/$alertId/resolve'),
      headers: _headers,
    );
    final body = jsonDecode(response.body);
    return {'ok': response.statusCode == 200, 'message': body['message'] ?? body['detail'] ?? 'Action completed'};
  }

  Future<Map<String, dynamic>> submitCountingSession({
    required String busId,
    required String routeId,
    required String sessionId,
    required int boardingCount,
    required int alightingCount,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/authority/passenger-counting/session'),
      headers: _headers,
      body: jsonEncode({
        'bus_id': busId,
        'route_id': routeId,
        'session_id': sessionId,
        'boarding_count': boardingCount,
        'alighting_count': alightingCount,
      }),
    );
    final body = jsonDecode(response.body);
    return {'ok': response.statusCode == 200, 'message': body['detail'] ?? 'Session recorded', ...body};
  }

  Future<Map<String, dynamic>> fetchSchedule(String routeId, {String dayType = 'WEEKDAY'}) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/schedules/$routeId?day_type=$dayType'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    return {};
  }

  Future<List<DispatchRecommendation>> fetchPendingDispatches() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/dispatches/pending'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['dispatches'] as List;
      return list.map((d) => DispatchRecommendation.fromJson(d)).toList();
    }
    return [];
  }

  Future<bool> decideDispatch(String recommendationId, String decision) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/dispatches/$recommendationId/decide'),
      headers: _headers,
      body: jsonEncode({'decision': decision}),
    );
    return response.statusCode == 200;
  }

  Future<FuelSummary?> fetchFuelSummary() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/fuel/summary'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      return FuelSummary.fromJson(jsonDecode(response.body));
    }
    return null;
  }

  Future<List<RouteDemandItem>> fetchRouteDemand() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/authority/route-demand'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['routes'] as List;
      return list.map((r) => RouteDemandItem.fromJson(r)).toList();
    }
    return [];
  }

  Future<PassengerCountingSummary?> fetchPassengerCountingSummary() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/authority/passenger-counting'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      return PassengerCountingSummary.fromJson(jsonDecode(response.body));
    }
    return null;
  }

  Future<JourneySearchResult?> searchJourneys(
      String source, String destination) async {
    final uri = Uri.parse('$baseUrl/api/journeys/search').replace(
      queryParameters: {
        'source': source.trim(),
        'destination': destination.trim(),
      },
    );
    final response = await http.get(uri, headers: _headers);
    if (response.statusCode == 200) {
      return JourneySearchResult.fromJson(jsonDecode(response.body));
    }
    return null;
  }

  Future<Map<String, dynamic>> saveTrip(
      String sourceStop, String destinationStop) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/trips/save'),
      headers: _headers,
      body: jsonEncode({
        'source_stop': sourceStop.trim(),
        'destination_stop': destinationStop.trim(),
      }),
    );
    Map<String, dynamic> body = {};
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } catch (_) {}
    final ok = response.statusCode == 200 || response.statusCode == 201;
    return {
      'ok': ok,
      'statusCode': response.statusCode,
      'message': body['detail'] ?? (ok ? 'Trip saved' : 'Failed to save trip (${response.statusCode})'),
      ...body,
    };
  }

  Future<List<SavedTrip>> fetchSavedTrips() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/trips/saved'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final list = data['saved_trips'] as List? ?? [];
      return list.map((t) => SavedTrip.fromJson(t)).toList();
    }
    throw Exception('Failed to load saved trips (${response.statusCode})');
  }

  Future<StopDetailsResponse?> fetchBusesForStop(String stopId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/stops/${Uri.encodeComponent(stopId)}/buses'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      return StopDetailsResponse.fromJson(jsonDecode(response.body));
    }
    return null;
  }

  Future<BusUpcomingResponse?> fetchBusUpcomingStops(String busId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/buses/$busId/upcoming-stops'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      return BusUpcomingResponse.fromJson(jsonDecode(response.body));
    }
    return null;
  }
}

