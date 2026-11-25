class UserProfile {
  final String uid;
  final String email;
  final String role;
  final String displayName;
  final double expiresAt;

  UserProfile({
    required this.uid,
    required this.email,
    required this.role,
    required this.displayName,
    required this.expiresAt,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      uid: json['uid'] ?? '',
      email: json['email'] ?? '',
      role: json['role'] ?? 'passenger',
      displayName: json['display_name'] ?? 'Passenger',
      expiresAt: (json['expires_at'] is num) ? (json['expires_at'] as num).toDouble() : 0.0,
    );
  }

  Map<String, dynamic> toJson() => {
    'uid': uid,
    'email': email,
    'role': role,
    'display_name': displayName,
    'expires_at': expiresAt,
  };
}

class BusStop {
  final String stopId;
  final int stopOrder;
  final String stopName;
  final double latitude;
  final double longitude;

  BusStop({
    required this.stopId,
    required this.stopOrder,
    required this.stopName,
    required this.latitude,
    required this.longitude,
  });

  factory BusStop.fromJson(Map<String, dynamic> json) {
    return BusStop(
      stopId: json['stop_id'] ?? '',
      stopOrder: json['stop_order'] ?? 0,
      stopName: json['stop_name'] ?? '',
      latitude: (json['latitude'] is num) ? (json['latitude'] as num).toDouble() : 12.9716,
      longitude: (json['longitude'] is num) ? (json['longitude'] as num).toDouble() : 77.5945,
    );
  }
}

class TransitRoute {
  final String routeId;
  final String routeName;
  final String demandProfile;
  final int baseCycleTimeMins;
  final int totalStops;
  final List<BusStop> stops;

  TransitRoute({
    required this.routeId,
    required this.routeName,
    required this.demandProfile,
    required this.baseCycleTimeMins,
    required this.totalStops,
    required this.stops,
  });

  factory TransitRoute.fromJson(Map<String, dynamic> json) {
    var rawStops = json['stops'] as List? ?? [];
    List<BusStop> stopsList = rawStops.map((s) => BusStop.fromJson(s)).toList();
    return TransitRoute(
      routeId: json['route_id'] ?? '',
      routeName: json['route_name'] ?? '',
      demandProfile: json['demand_profile'] ?? 'MODERATE_DEMAND',
      baseCycleTimeMins: json['base_cycle_time_mins'] ?? 60,
      totalStops: json['total_stops'] ?? stopsList.length,
      stops: stopsList,
    );
  }
}

class BusState {
  final String busId;
  final String plateNumber;
  final int capacity;
  final int currentOccupancy;
  final double occupancyPct;
  final String occupancyStatus; // NORMAL, WARNING, CRITICAL
  final String? currentRouteId;
  final String? lastStopId;
  final String? lastStopName;
  final String status;
  final bool isReliefBus;
  final String dataProvenance;

  BusState({
    required this.busId,
    required this.plateNumber,
    required this.capacity,
    required this.currentOccupancy,
    required this.occupancyPct,
    required this.occupancyStatus,
    this.currentRouteId,
    this.lastStopId,
    this.lastStopName,
    required this.status,
    required this.isReliefBus,
    required this.dataProvenance,
  });

  int get availableCapacity => (capacity - currentOccupancy).clamp(0, capacity);

  factory BusState.fromJson(Map<String, dynamic> json) {
    return BusState(
      busId: json['bus_id'] ?? '',
      plateNumber: json['plate_number'] ?? '',
      capacity: json['capacity'] ?? 50,
      currentOccupancy: json['current_occupancy'] ?? 0,
      occupancyPct: (json['occupancy_pct'] is num) ? (json['occupancy_pct'] as num).toDouble() : 0.0,
      occupancyStatus: json['occupancy_status'] ?? 'NORMAL',
      currentRouteId: json['current_route_id'],
      lastStopId: json['last_stop_id'],
      lastStopName: json['last_stop_name'],
      status: json['status'] ?? 'IN_SERVICE',
      isReliefBus: json['is_relief_bus'] ?? false,
      dataProvenance: json['data_provenance'] ?? 'CURRENT_CV_READING',
    );
  }
}

class BusLocation {
  final String busId;
  final double latitude;
  final double longitude;
  final double heading;
  final double speedKmh;
  final String? nextStopId;
  final double? estimatedArrivalMins;
  final String dataProvenance;

  BusLocation({
    required this.busId,
    required this.latitude,
    required this.longitude,
    required this.heading,
    required this.speedKmh,
    this.nextStopId,
    this.estimatedArrivalMins,
    required this.dataProvenance,
  });

  factory BusLocation.fromJson(Map<String, dynamic> json) {
    return BusLocation(
      busId: json['bus_id'] ?? '',
      latitude: (json['latitude'] is num) ? (json['latitude'] as num).toDouble() : 12.9770,
      longitude: (json['longitude'] is num) ? (json['longitude'] as num).toDouble() : 77.5713,
      heading: (json['heading'] is num) ? (json['heading'] as num).toDouble() : 0.0,
      speedKmh: (json['speed_kmh'] is num) ? (json['speed_kmh'] as num).toDouble() : 0.0,
      nextStopId: json['next_stop_id'],
      estimatedArrivalMins: (json['estimated_arrival_mins'] is num)
          ? (json['estimated_arrival_mins'] as num).toDouble()
          : null,
      dataProvenance: json['data_provenance'] ?? 'SIMULATED_LOCATION',
    );
  }
}

class StopForecast {
  final int stepAhead;
  final String targetStopId;
  final String targetStopName;
  final double predictedOccupancy;
  final int predictedOccupancyRounded;
  final String predictedStatus;

  StopForecast({
    required this.stepAhead,
    required this.targetStopId,
    required this.targetStopName,
    required this.predictedOccupancy,
    required this.predictedOccupancyRounded,
    required this.predictedStatus,
  });

  factory StopForecast.fromJson(Map<String, dynamic> json) {
    return StopForecast(
      stepAhead: json['step_ahead'] ?? 1,
      targetStopId: json['target_stop_id'] ?? '',
      targetStopName: json['target_stop_name'] ?? '',
      predictedOccupancy: (json['predicted_occupancy'] is num)
          ? (json['predicted_occupancy'] as num).toDouble()
          : 0.0,
      predictedOccupancyRounded: json['predicted_occupancy_rounded'] ?? 0,
      predictedStatus: json['predicted_status'] ?? 'NORMAL',
    );
  }
}

class CrowdingAlert {
  final String alertId;
  final String busId;
  final String routeId;
  final String? stopId;
  final String alertLevel; // WARNING, CRITICAL
  final int currentOccupancy;
  final int capacity;
  final double occupancyPct;
  final String alertStatus; // ACTIVE, ACKNOWLEDGED, RESOLVED
  final String? createdAt;
  final double? acknowledgedAt;
  final double? resolvedAt;

  CrowdingAlert({
    required this.alertId,
    required this.busId,
    required this.routeId,
    this.stopId,
    required this.alertLevel,
    required this.currentOccupancy,
    required this.capacity,
    required this.occupancyPct,
    required this.alertStatus,
    this.createdAt,
    this.acknowledgedAt,
    this.resolvedAt,
  });

  factory CrowdingAlert.fromJson(Map<String, dynamic> json) {
    return CrowdingAlert(
      alertId: json['alert_id'] ?? '',
      busId: json['bus_id'] ?? '',
      routeId: json['route_id'] ?? '',
      stopId: json['stop_id'],
      alertLevel: json['alert_level'] ?? 'WARNING',
      currentOccupancy: json['current_occupancy'] ?? 0,
      capacity: json['capacity'] ?? 50,
      occupancyPct: (json['occupancy_pct'] is num) ? (json['occupancy_pct'] as num).toDouble() : 0.0,
      alertStatus: json['alert_status'] ?? 'ACTIVE',
      createdAt: json['created_at']?.toString(),
      acknowledgedAt: (json['acknowledged_at'] is num) ? (json['acknowledged_at'] as num).toDouble() : null,
      resolvedAt: (json['resolved_at'] is num) ? (json['resolved_at'] as num).toDouble() : null,
    );
  }
}

class NearbyStop {
  final String stopId;
  final String stopName;
  final int stopOrder;
  final double latitude;
  final double longitude;
  final double? distanceKm;
  final List<String> routes;
  final List<Map<String, dynamic>> servingBuses;
  final double? nextArrivalMins;
  final String dataProvenance;

  NearbyStop({
    required this.stopId,
    required this.stopName,
    required this.stopOrder,
    required this.latitude,
    required this.longitude,
    this.distanceKm,
    required this.routes,
    required this.servingBuses,
    this.nextArrivalMins,
    required this.dataProvenance,
  });

  factory NearbyStop.fromJson(Map<String, dynamic> json) {
    return NearbyStop(
      stopId: json['stop_id'] ?? '',
      stopName: json['stop_name'] ?? '',
      stopOrder: json['stop_order'] ?? 0,
      latitude: (json['latitude'] is num) ? (json['latitude'] as num).toDouble() : 12.9716,
      longitude: (json['longitude'] is num) ? (json['longitude'] as num).toDouble() : 77.5945,
      distanceKm: (json['distance_km'] is num) ? (json['distance_km'] as num).toDouble() : null,
      routes: List<String>.from(json['routes'] ?? []),
      servingBuses: List<Map<String, dynamic>>.from(json['serving_buses'] ?? []),
      nextArrivalMins: (json['next_arrival_mins'] is num) ? (json['next_arrival_mins'] as num).toDouble() : null,
      dataProvenance: json['data_provenance'] ?? 'SURVEYED_STOPS',
    );
  }
}

class DispatchRecommendation {
  final String recommendationId;
  final String routeId;
  final String sourceBusId;
  final String recommendedReliefBusId;
  final String priority;
  final String recommendedAction;
  final String authorityDecision;

  DispatchRecommendation({
    required this.recommendationId,
    required this.routeId,
    required this.sourceBusId,
    required this.recommendedReliefBusId,
    required this.priority,
    required this.recommendedAction,
    required this.authorityDecision,
  });

  factory DispatchRecommendation.fromJson(Map<String, dynamic> json) {
    return DispatchRecommendation(
      recommendationId: json['recommendation_id'] ?? '',
      routeId: json['route_id'] ?? '',
      sourceBusId: json['source_bus_id'] ?? '',
      recommendedReliefBusId: json['recommended_relief_bus_id'] ?? 'NONE',
      priority: json['priority'] ?? 'MEDIUM',
      recommendedAction: json['recommended_action'] ?? 'DISPATCH_RELIEF_BUS',
      authorityDecision: json['authority_decision'] ?? 'PENDING',
    );
  }
}

class RouteDemandItem {
  final String routeId;
  final int totalBoardingDemand;
  final double averageOccupancyPct;
  final int maxOccupancy;
  final int warningOccurrences;
  final int criticalOccurrences;
  final String demandTier;

  RouteDemandItem({
    required this.routeId,
    required this.totalBoardingDemand,
    required this.averageOccupancyPct,
    required this.maxOccupancy,
    required this.warningOccurrences,
    required this.criticalOccurrences,
    required this.demandTier,
  });

  factory RouteDemandItem.fromJson(Map<String, dynamic> json) {
    return RouteDemandItem(
      routeId: json['route_id'] ?? '',
      totalBoardingDemand: json['total_boarding_demand'] ?? 0,
      averageOccupancyPct: (json['average_occupancy_pct'] is num) ? (json['average_occupancy_pct'] as num).toDouble() : 0.0,
      maxOccupancy: json['max_occupancy'] ?? 0,
      warningOccurrences: json['warning_occurrences'] ?? 0,
      criticalOccurrences: json['critical_occurrences'] ?? 0,
      demandTier: json['demand_tier'] ?? 'MODERATE_DEMAND',
    );
  }
}

class FuelSummary {
  final double totalFuelLitres;
  final double meanFuelPerStop;
  final int recordsCount;
  final String formula;
  final String dataProvenance;
  final List<Map<String, dynamic>> busWise;
  final List<Map<String, dynamic>> routeWise;

  FuelSummary({
    required this.totalFuelLitres,
    required this.meanFuelPerStop,
    required this.recordsCount,
    required this.formula,
    required this.dataProvenance,
    required this.busWise,
    required this.routeWise,
  });

  factory FuelSummary.fromJson(Map<String, dynamic> json) {
    return FuelSummary(
      totalFuelLitres: (json['total_fuel_litres'] is num) ? (json['total_fuel_litres'] as num).toDouble() : 0.0,
      meanFuelPerStop: (json['mean_fuel_per_stop'] is num) ? (json['mean_fuel_per_stop'] as num).toDouble() : 0.0,
      recordsCount: json['records_count'] ?? 0,
      formula: json['formula'] ?? '0.200 + 0.004 * occupancy',
      dataProvenance: json['data_provenance'] ?? 'SYNTHETIC_ESTIMATED_TELEMETRY',
      busWise: List<Map<String, dynamic>>.from(json['bus_wise'] ?? []),
      routeWise: List<Map<String, dynamic>>.from(json['route_wise'] ?? []),
    );
  }
}

class PassengerCountingSummary {
  final String detector;
  final String tracker;
  final int recordsCount;
  final int totalBoarding;
  final int totalAlighting;
  final int netOccupancyDelta;
  final String dataProvenance;

  PassengerCountingSummary({
    required this.detector,
    required this.tracker,
    required this.recordsCount,
    required this.totalBoarding,
    required this.totalAlighting,
    required this.netOccupancyDelta,
    required this.dataProvenance,
  });

  factory PassengerCountingSummary.fromJson(Map<String, dynamic> json) {
    return PassengerCountingSummary(
      detector: json['detector'] ?? 'YOLOv8n',
      tracker: json['tracker'] ?? 'ByteTrack',
      recordsCount: json['records_count'] ?? 0,
      totalBoarding: json['total_boarding'] ?? 0,
      totalAlighting: json['total_alighting'] ?? 0,
      netOccupancyDelta: json['net_occupancy_delta'] ?? 0,
      dataProvenance: json['data_provenance'] ?? 'YOLO_BYTETRACK_MODULE4_INTEGRATION',
    );
  }
}

