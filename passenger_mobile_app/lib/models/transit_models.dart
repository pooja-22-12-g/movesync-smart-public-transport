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
  final String? routeName;
  final String? lastStopId;
  final String? lastStopName;
  final String? nextStopId;
  final String? nextStopName;
  final String? currentTripId;
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
    this.routeName,
    this.lastStopId,
    this.lastStopName,
    this.nextStopId,
    this.nextStopName,
    this.currentTripId,
    required this.status,
    required this.isReliefBus,
    required this.dataProvenance,
  });

  int get availableCapacity => (capacity - currentOccupancy).clamp(0, capacity);

  factory BusState.fromJson(Map<String, dynamic> json) {
    return BusState(
      busId: (json['bus_id'] ?? '').toString(),
      plateNumber: (json['plate_number'] ?? '').toString(),
      capacity: (json['capacity'] is num) ? (json['capacity'] as num).toInt() : 60,
      currentOccupancy: (json['current_occupancy'] is num) ? (json['current_occupancy'] as num).toInt() : 0,
      occupancyPct: (json['occupancy_pct'] is num) ? (json['occupancy_pct'] as num).toDouble() : 0.0,
      occupancyStatus: (json['occupancy_status'] ?? 'NORMAL').toString(),
      currentRouteId: json['current_route_id']?.toString(),
      routeName: json['route_name']?.toString(),
      lastStopId: json['last_stop_id']?.toString(),
      lastStopName: json['last_stop_name']?.toString(),
      nextStopId: json['next_stop_id']?.toString(),
      nextStopName: json['next_stop_name']?.toString(),
      currentTripId: json['current_trip_id']?.toString(),
      status: (json['status'] ?? 'IN_SERVICE').toString(),
      isReliefBus: json['is_relief_bus'] == true,
      dataProvenance: (json['data_provenance'] ?? 'SYNTHETIC_DATASET_SNAPSHOT').toString(),
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
  final double? latitude;
  final double? longitude;
  final bool gpsAvailable;
  final double? distanceKm;
  final List<String> routes;
  final List<Map<String, dynamic>> servingBuses;
  final double? nextArrivalMins;
  final String dataProvenance;

  NearbyStop({
    required this.stopId,
    required this.stopName,
    required this.stopOrder,
    this.latitude,
    this.longitude,
    required this.gpsAvailable,
    this.distanceKm,
    required this.routes,
    required this.servingBuses,
    this.nextArrivalMins,
    required this.dataProvenance,
  });

  factory NearbyStop.fromJson(Map<String, dynamic> json) {
    final lat = (json['latitude'] is num) ? (json['latitude'] as num).toDouble() : null;
    final lon = (json['longitude'] is num) ? (json['longitude'] as num).toDouble() : null;
    return NearbyStop(
      stopId: (json['stop_id'] ?? '').toString(),
      stopName: (json['stop_name'] ?? '').toString(),
      stopOrder: (json['stop_order'] is num) ? (json['stop_order'] as num).toInt() : 0,
      latitude: lat,
      longitude: lon,
      gpsAvailable: json['gps_available'] ?? (lat != null && lon != null),
      distanceKm: (json['distance_km'] is num) ? (json['distance_km'] as num).toDouble() : null,
      routes: List<String>.from(json['routes'] ?? []),
      servingBuses: List<Map<String, dynamic>>.from(json['serving_buses'] ?? []),
      nextArrivalMins: (json['next_arrival_mins'] is num) ? (json['next_arrival_mins'] as num).toDouble() : null,
      dataProvenance: (json['data_provenance'] ?? 'DATASET_STOP_SEQUENCE_NO_GPS').toString(),
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

class JourneyOption {
  final String busId;
  final String tripId;
  final String routeId;
  final String routeName;
  final String corridorName;
  final String boardingStop;
  final String boardingStopId;
  final int boardingSequence;
  final String destinationStop;
  final String destinationStopId;
  final int destinationSequence;
  final String boardingTime;
  final String destinationTime;
  final int currentOccupancy;
  final int busCapacity;
  final int availableSeats;
  final double occupancyPct;
  final String crowdStatus;
  final List<String> intermediateStops;
  final int totalStops;
  final String dataProvenance;

  JourneyOption({
    required this.busId,
    required this.tripId,
    required this.routeId,
    required this.routeName,
    required this.corridorName,
    required this.boardingStop,
    required this.boardingStopId,
    required this.boardingSequence,
    required this.destinationStop,
    required this.destinationStopId,
    required this.destinationSequence,
    required this.boardingTime,
    required this.destinationTime,
    required this.currentOccupancy,
    required this.busCapacity,
    required this.availableSeats,
    required this.occupancyPct,
    required this.crowdStatus,
    required this.intermediateStops,
    required this.totalStops,
    required this.dataProvenance,
  });

  factory JourneyOption.fromJson(Map<String, dynamic> json) {
    final bStop = (json['boarding_stop'] ?? '').toString();
    final dStop = (json['destination_stop'] ?? '').toString();
    final bSeq = (json['boarding_sequence'] is num) ? (json['boarding_sequence'] as num).toInt() : 0;
    final dSeq = (json['destination_sequence'] is num) ? (json['destination_sequence'] as num).toInt() : 0;
    final cap = (json['bus_capacity'] is num) ? (json['bus_capacity'] as num).toInt() : 60;
    final occ = (json['current_occupancy'] is num) ? (json['current_occupancy'] as num).toInt() : 0;
    final inter = List<String>.from(json['intermediate_stops'] ?? []);
    return JourneyOption(
      busId: (json['bus_id'] ?? '').toString(),
      tripId: (json['trip_id'] ?? '').toString(),
      routeId: (json['route_id'] ?? '').toString(),
      routeName: (json['route_name'] ?? '$bStop → $dStop').toString(),
      corridorName: (json['corridor_name'] ?? 'KR Market → Anekal').toString(),
      boardingStop: bStop,
      boardingStopId: (json['boarding_stop_id'] ?? '').toString(),
      boardingSequence: bSeq,
      destinationStop: dStop,
      destinationStopId: (json['destination_stop_id'] ?? '').toString(),
      destinationSequence: dSeq,
      boardingTime: (json['boarding_time'] ?? '').toString(),
      destinationTime: (json['destination_time'] ?? '').toString(),
      currentOccupancy: occ,
      busCapacity: cap,
      availableSeats: (json['available_seats'] is num)
          ? (json['available_seats'] as num).toInt()
          : (cap - occ).clamp(0, cap),
      occupancyPct: (json['occupancy_pct'] is num)
          ? (json['occupancy_pct'] as num).toDouble()
          : 0.0,
      crowdStatus: (json['crowd_status'] ?? 'Low').toString(),
      intermediateStops: inter,
      totalStops: (json['total_stops'] is num)
          ? (json['total_stops'] as num).toInt()
          : (dSeq > bSeq && bSeq > 0 ? dSeq - bSeq + 1 : inter.length + 2),
      dataProvenance: (json['data_provenance'] ?? 'DATASET_HISTORICAL_SIMULATION').toString(),
    );
  }
}

class JourneySearchResult {
  final bool valid;
  final String? message;
  final String sourceStop;
  final String destinationStop;
  final List<String> intermediateStops;
  final int count;
  final List<JourneyOption> journeys;

  JourneySearchResult({
    required this.valid,
    this.message,
    required this.sourceStop,
    required this.destinationStop,
    required this.intermediateStops,
    required this.count,
    required this.journeys,
  });

  factory JourneySearchResult.fromJson(Map<String, dynamic> json) {
    final rawJourneys = json['journeys'] as List? ?? [];
    return JourneySearchResult(
      valid: json['valid'] ?? false,
      message: json['message'],
      sourceStop: json['source_stop'] ?? '',
      destinationStop: json['destination_stop'] ?? '',
      intermediateStops: List<String>.from(json['intermediate_stops'] ?? []),
      count: json['count'] ?? rawJourneys.length,
      journeys: rawJourneys.map((j) => JourneyOption.fromJson(j)).toList(),
    );
  }
}

class SavedTrip {
  final String savedTripId;
  final String sourceStop;
  final String destinationStop;
  final String? selectedBusId;
  final String? selectedTripId;
  final JourneyOption? selectedJourney;
  final String createdAt;
  final bool valid;
  final String? message;
  final List<String> intermediateStops;
  final List<JourneyOption> matchingBuses;

  SavedTrip({
    required this.savedTripId,
    required this.sourceStop,
    required this.destinationStop,
    this.selectedBusId,
    this.selectedTripId,
    this.selectedJourney,
    required this.createdAt,
    required this.valid,
    this.message,
    required this.intermediateStops,
    required this.matchingBuses,
  });

  factory SavedTrip.fromJson(Map<String, dynamic> json) {
    final rawBuses = json['matching_buses'] as List? ?? [];
    final rawSel = json['selected_journey'];
    return SavedTrip(
      savedTripId: (json['saved_trip_id'] ?? '').toString(),
      sourceStop: (json['source_stop'] ?? '').toString(),
      destinationStop: (json['destination_stop'] ?? '').toString(),
      selectedBusId: json['selected_bus_id']?.toString(),
      selectedTripId: json['selected_trip_id']?.toString(),
      selectedJourney: rawSel is Map<String, dynamic> ? JourneyOption.fromJson(rawSel) : null,
      createdAt: (json['created_at'] ?? '').toString(),
      valid: json['valid'] ?? true,
      message: json['message']?.toString(),
      intermediateStops: List<String>.from(json['intermediate_stops'] ?? []),
      matchingBuses: rawBuses.map((j) => JourneyOption.fromJson(j)).toList(),
    );
  }
}

class UpcomingStop {
  final String stopId;
  final String stopName;
  final int stopSequence;
  final int expectedBoarding;
  final int expectedAlighting;
  final int expectedOccupancy;
  final int availableSeats;
  final int busCapacity;
  final double occupancyPct;
  final String crowdStatus;
  final String expectedTime;
  final bool isNextStop;
  final bool predictionAvailable;
  final String predictionSource;

  UpcomingStop({
    required this.stopId,
    required this.stopName,
    required this.stopSequence,
    required this.expectedBoarding,
    required this.expectedAlighting,
    required this.expectedOccupancy,
    required this.availableSeats,
    required this.busCapacity,
    required this.occupancyPct,
    required this.crowdStatus,
    required this.expectedTime,
    required this.isNextStop,
    required this.predictionAvailable,
    required this.predictionSource,
  });

  factory UpcomingStop.fromJson(Map<String, dynamic> json) {
    final cap = (json['bus_capacity'] is num) ? (json['bus_capacity'] as num).toInt() : 60;
    final expOcc = (json['expected_occupancy'] is num) ? (json['expected_occupancy'] as num).toInt() : 0;
    final avail = (json['available_seats'] is num)
        ? (json['available_seats'] as num).toInt()
        : (cap - expOcc).clamp(0, cap);
    return UpcomingStop(
      stopId: (json['stop_id'] ?? '').toString(),
      stopName: (json['stop_name'] ?? '').toString(),
      stopSequence: (json['stop_sequence'] is num) ? (json['stop_sequence'] as num).toInt() : 0,
      expectedBoarding: (json['expected_boarding'] is num) ? (json['expected_boarding'] as num).toInt() : 0,
      expectedAlighting: (json['expected_alighting'] is num) ? (json['expected_alighting'] as num).toInt() : 0,
      expectedOccupancy: expOcc,
      availableSeats: avail,
      busCapacity: cap,
      occupancyPct: (json['occupancy_pct'] is num)
          ? (json['occupancy_pct'] as num).toDouble()
          : 0.0,
      crowdStatus: (json['crowd_status'] ?? 'Low').toString(),
      expectedTime: (json['expected_time'] ?? '').toString(),
      isNextStop: json['is_next_stop'] == true,
      predictionAvailable: json['prediction_available'] ?? true,
      predictionSource: (json['prediction_source'] ?? 'RANDOM_FOREST_ML').toString(),
    );
  }
}

class LessCrowdedAlternative {
  final String busId;
  final String routeId;
  final String currentStop;
  final int currentOccupancy;
  final int busCapacity;
  final double occupancyPct;
  final String crowdStatus;

  LessCrowdedAlternative({
    required this.busId,
    required this.routeId,
    required this.currentStop,
    required this.currentOccupancy,
    required this.busCapacity,
    required this.occupancyPct,
    required this.crowdStatus,
  });

  factory LessCrowdedAlternative.fromJson(Map<String, dynamic> json) {
    return LessCrowdedAlternative(
      busId: json['bus_id'] ?? '',
      routeId: json['route_id'] ?? '',
      currentStop: json['current_stop'] ?? '',
      currentOccupancy: json['current_occupancy'] ?? 0,
      busCapacity: json['bus_capacity'] ?? 60,
      occupancyPct: (json['occupancy_pct'] is num)
          ? (json['occupancy_pct'] as num).toDouble()
          : 0.0,
      crowdStatus: json['crowd_status'] ?? 'Low',
    );
  }
}

class StopBusInfo {
  final String busId;
  final String tripId;
  final String routeId;
  final String routeName;
  final String currentStopId;
  final String currentStopName;
  final int currentStopSequence;
  final String? nextStopName;
  final int currentOccupancy;
  final int busCapacity;
  final int availableSeats;
  final double occupancyPct;
  final String crowdStatus;
  final bool upcomingToStop;

  StopBusInfo({
    required this.busId,
    required this.tripId,
    required this.routeId,
    required this.routeName,
    required this.currentStopId,
    required this.currentStopName,
    required this.currentStopSequence,
    this.nextStopName,
    required this.currentOccupancy,
    required this.busCapacity,
    required this.availableSeats,
    required this.occupancyPct,
    required this.crowdStatus,
    required this.upcomingToStop,
  });

  factory StopBusInfo.fromJson(Map<String, dynamic> json) {
    final cap = (json['bus_capacity'] is num) ? (json['bus_capacity'] as num).toInt() : 60;
    final occ = (json['current_occupancy'] is num) ? (json['current_occupancy'] as num).toInt() : 0;
    return StopBusInfo(
      busId: (json['bus_id'] ?? '').toString(),
      tripId: (json['trip_id'] ?? '').toString(),
      routeId: (json['route_id'] ?? '').toString(),
      routeName: (json['route_name'] ?? 'KR Market → Anekal').toString(),
      currentStopId: (json['current_stop_id'] ?? '').toString(),
      currentStopName: (json['current_stop_name'] ?? '').toString(),
      currentStopSequence: (json['current_stop_sequence'] is num) ? (json['current_stop_sequence'] as num).toInt() : 0,
      nextStopName: json['next_stop_name']?.toString(),
      currentOccupancy: occ,
      busCapacity: cap,
      availableSeats: (json['available_seats'] is num) ? (json['available_seats'] as num).toInt() : (cap - occ).clamp(0, cap),
      occupancyPct: (json['occupancy_pct'] is num) ? (json['occupancy_pct'] as num).toDouble() : 0.0,
      crowdStatus: (json['crowd_status'] ?? 'Low').toString(),
      upcomingToStop: json['upcoming_to_stop'] == true,
    );
  }
}

class StopDetailsResponse {
  final bool found;
  final NearbyStop? stop;
  final int count;
  final List<StopBusInfo> buses;

  StopDetailsResponse({
    required this.found,
    this.stop,
    required this.count,
    required this.buses,
  });

  factory StopDetailsResponse.fromJson(Map<String, dynamic> json) {
    final rawBuses = json['buses'] as List? ?? [];
    return StopDetailsResponse(
      found: json['found'] == true,
      stop: json['stop'] != null ? NearbyStop.fromJson(json['stop']) : null,
      count: (json['count'] is num) ? (json['count'] as num).toInt() : rawBuses.length,
      buses: rawBuses.map((b) => StopBusInfo.fromJson(b)).toList(),
    );
  }
}

class BusUpcomingResponse {
  final String busId;
  final String tripId;
  final String routeId;
  final String currentStopId;
  final String currentStopName;
  final int currentStopSequence;
  final int currentOccupancy;
  final int busCapacity;
  final int availableSeats;
  final double occupancyPct;
  final String crowdStatus;
  final String currentOccupancySource;
  final String expectedOccupancySource;
  final bool actualOccupancyAvailable;
  final int? actualOccupancy;
  final bool predictionsAvailable;
  final String predictionModel;
  final String? message;
  final String dataProvenance;
  final List<UpcomingStop> upcomingStops;
  final List<LessCrowdedAlternative> lessCrowdedAlternatives;

  BusUpcomingResponse({
    required this.busId,
    required this.tripId,
    required this.routeId,
    required this.currentStopId,
    required this.currentStopName,
    required this.currentStopSequence,
    required this.currentOccupancy,
    required this.busCapacity,
    required this.availableSeats,
    required this.occupancyPct,
    required this.crowdStatus,
    required this.currentOccupancySource,
    required this.expectedOccupancySource,
    required this.actualOccupancyAvailable,
    this.actualOccupancy,
    required this.predictionsAvailable,
    required this.predictionModel,
    this.message,
    required this.dataProvenance,
    required this.upcomingStops,
    required this.lessCrowdedAlternatives,
  });

  factory BusUpcomingResponse.fromJson(Map<String, dynamic> json) {
    final rawUpcoming = json['upcoming_stops'] as List? ?? [];
    final rawAlt = json['less_crowded_alternatives'] as List? ?? [];
    final cap = (json['bus_capacity'] is num) ? (json['bus_capacity'] as num).toInt() : 60;
    final curOcc = (json['current_occupancy'] is num) ? (json['current_occupancy'] as num).toInt() : 0;
    return BusUpcomingResponse(
      busId: (json['bus_id'] ?? '').toString(),
      tripId: (json['trip_id'] ?? '').toString(),
      routeId: (json['route_id'] ?? '').toString(),
      currentStopId: (json['current_stop_id'] ?? '').toString(),
      currentStopName: (json['current_stop_name'] ?? '').toString(),
      currentStopSequence: (json['current_stop_sequence'] is num) ? (json['current_stop_sequence'] as num).toInt() : 0,
      currentOccupancy: curOcc,
      busCapacity: cap,
      availableSeats: (json['available_seats'] is num)
          ? (json['available_seats'] as num).toInt()
          : (cap - curOcc).clamp(0, cap),
      occupancyPct: (json['occupancy_pct'] is num)
          ? (json['occupancy_pct'] as num).toDouble()
          : 0.0,
      crowdStatus: (json['crowd_status'] ?? 'Low').toString(),
      currentOccupancySource: (json['current_occupancy_source'] ?? 'DATASET_SIMULATED').toString(),
      expectedOccupancySource: (json['expected_occupancy_source'] ?? 'RANDOM_FOREST_ML').toString(),
      actualOccupancyAvailable: json['actual_occupancy_available'] == true,
      actualOccupancy: (json['actual_occupancy'] is num) ? (json['actual_occupancy'] as num).toInt() : null,
      predictionsAvailable: json['predictions_available'] ?? rawUpcoming.isNotEmpty,
      predictionModel: (json['prediction_model'] ?? 'RandomForestRegressor').toString(),
      message: json['message']?.toString(),
      dataProvenance: (json['data_provenance'] ?? 'DATASET_SIMULATED_CURRENT_AND_RF_ML_PREDICTION').toString(),
      upcomingStops: rawUpcoming.map((s) => UpcomingStop.fromJson(s)).toList(),
      lessCrowdedAlternatives: rawAlt
          .map((a) => LessCrowdedAlternative.fromJson(a))
          .toList(),
    );
  }
}

