import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:passenger_mobile_app/main.dart';
import 'package:passenger_mobile_app/models/transit_models.dart';
import 'package:passenger_mobile_app/providers/transit_provider.dart';
import 'package:passenger_mobile_app/screens/journey_details_screen.dart';
import 'package:passenger_mobile_app/screens/my_trips_screen.dart';
import 'package:passenger_mobile_app/screens/tracking_screen.dart';

class _FakeTransitProvider extends TransitProvider {
  BusUpcomingResponse? _fakeUpcoming;
  List<SavedTrip> _fakeSaved = [];

  void setFakeUpcoming(BusUpcomingResponse resp) {
    _fakeUpcoming = resp;
  }

  void setFakeSaved(List<SavedTrip> trips) {
    _fakeSaved = trips;
  }

  @override
  BusUpcomingResponse? get busUpcomingResponse => _fakeUpcoming;

  @override
  List<SavedTrip> get savedTrips => _fakeSaved;

  @override
  bool get isLoadingUpcoming => false;

  @override
  bool get isLoadingSavedTrips => false;

  @override
  Future<void> selectBus(BusState bus, {JourneyOption? journey}) async {}

  @override
  Future<void> loadSavedTrips() async {}
}

void main() {
  testWidgets('App renders login screen when unauthenticated', (WidgetTester tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => TransitProvider()),
        ],
        child: const SmartPassengerApp(),
      ),
    );

    expect(find.text('MoveSync'), findsOneWidget);
    expect(find.text('Smart Mobility. Better Journeys.'), findsOneWidget);
    expect(find.text('Passenger Login'), findsOneWidget);
    expect(find.text('Authority Login'), findsOneWidget);
  });

  testWidgets('JourneyDetailsScreen shows selected segment stops without KR Market override', (WidgetTester tester) async {
    final journey = JourneyOption.fromJson({
      'bus_id': 'KA-BUS-007',
      'trip_id': 3642,
      'route_id': 'KR_MARKET_ANEKAL_VIA_ECITY',
      'route_name': 'Kudlu Gate → Anekal',
      'corridor_name': 'KR Market → Anekal',
      'boarding_stop': 'Kudlu Gate',
      'boarding_stop_id': 'S20',
      'boarding_sequence': 20,
      'destination_stop': 'Anekal',
      'destination_stop_id': 'S50',
      'destination_sequence': 50,
      'boarding_time': '2026-10-31 19:45:00',
      'destination_time': '2026-10-31 20:50:00',
      'current_occupancy': 36,
      'bus_capacity': 60,
      'available_seats': 24,
      'occupancy_pct': 60.0,
      'crowd_status': 'Moderate',
      'intermediate_stops': ['Singasandra', 'Hosa Road', 'Konappana Agrahara', 'Electronic City'],
      'total_stops': 6,
    });

    await tester.pumpWidget(
      ChangeNotifierProvider<TransitProvider>(
        create: (_) => _FakeTransitProvider(),
        child: MaterialApp(home: JourneyDetailsScreen(journey: journey)),
      ),
    );

    expect(find.text('Kudlu Gate → Anekal'), findsOneWidget);
    expect(find.text('Singasandra'), findsOneWidget);
    expect(find.text('24 seats'), findsOneWidget);
    expect(find.text('Save Trip'), findsOneWidget);
  });

  testWidgets('TrackingScreen renders upcoming stops and Random Forest ML expected occupancy', (WidgetTester tester) async {
    final fakeProvider = _FakeTransitProvider();
    final bus = BusState.fromJson({
      'bus_id': 'KA-BUS-005',
      'plate_number': 'KA-01-F-005',
      'capacity': 60,
      'current_occupancy': 44,
      'occupancy_pct': 73.3,
      'occupancy_status': 'NORMAL',
      'current_route_id': 'KR_MARKET_ANEKAL_VIA_ECITY',
      'last_stop_id': 'S14',
      'last_stop_name': 'Kudure Mukha Colony',
      'current_trip_id': '3630',
    });
    fakeProvider.setFakeUpcoming(BusUpcomingResponse.fromJson({
      'bus_id': 'KA-BUS-005',
      'trip_id': 3630,
      'route_id': 'KR_MARKET_ANEKAL_VIA_ECITY',
      'current_stop_id': 'S14',
      'current_stop_name': 'Kudure Mukha Colony',
      'current_stop_sequence': 14,
      'current_occupancy': 44,
      'bus_capacity': 60,
      'available_seats': 16,
      'occupancy_pct': 73.3,
      'crowd_status': 'Moderate',
      'predictions_available': true,
      'actual_occupancy_available': false,
      'upcoming_stops': [
        {
          'stop_id': 'S15',
          'stop_name': 'Krupanidhi College',
          'stop_sequence': 15,
          'expected_boarding': 6,
          'expected_alighting': 4,
          'expected_occupancy': 46,
          'available_seats': 14,
          'bus_capacity': 60,
          'occupancy_pct': 76.7,
          'crowd_status': 'High',
          'expected_time': '2026-10-31 19:20:00',
          'is_next_stop': true,
          'prediction_available': true,
        },
      ],
      'less_crowded_alternatives': [],
    }));

    await tester.pumpWidget(
      ChangeNotifierProvider<TransitProvider>.value(
        value: fakeProvider,
        child: MaterialApp(home: TrackingScreen(bus: bus)),
      ),
    );
    await tester.pump();

    expect(find.text('Krupanidhi College'), findsOneWidget);
    expect(find.text('NEXT STOP'), findsOneWidget);
    expect(find.textContaining('Expected (ML): 46 / 60 (77%)'), findsOneWidget);
    expect(find.textContaining('14 seats free'), findsOneWidget);
    expect(find.text('High'), findsOneWidget);
    expect(find.textContaining('Actual Occupancy: Not available'), findsOneWidget);
  });

  testWidgets('MyTripsScreen shows saved segment and opens JourneyDetailsScreen on tap', (WidgetTester tester) async {
    final fakeProvider = _FakeTransitProvider();
    fakeProvider.setFakeSaved([
      SavedTrip.fromJson({
        'saved_trip_id': 'SAVED_1',
        'source_stop': 'Kudlu Gate',
        'destination_stop': 'Anekal',
        'selected_bus_id': 'KA-BUS-007',
        'selected_trip_id': '3642',
        'created_at': 1795624848.9,
        'valid': true,
        'intermediate_stops': ['Singasandra', 'Hosa Road'],
        'selected_journey': {
          'bus_id': 'KA-BUS-007',
          'trip_id': 3642,
          'route_id': 'KR_MARKET_ANEKAL_VIA_ECITY',
          'route_name': 'Kudlu Gate → Anekal',
          'boarding_stop': 'Kudlu Gate',
          'boarding_stop_id': 'S20',
          'boarding_sequence': 20,
          'destination_stop': 'Anekal',
          'destination_stop_id': 'S50',
          'destination_sequence': 50,
          'boarding_time': '19:45',
          'destination_time': '20:50',
          'current_occupancy': 30,
          'bus_capacity': 60,
          'occupancy_pct': 50.0,
          'crowd_status': 'Moderate',
          'intermediate_stops': ['Singasandra', 'Hosa Road'],
          'total_stops': 4,
        },
        'matching_buses': [],
      }),
    ]);

    await tester.pumpWidget(
      ChangeNotifierProvider<TransitProvider>.value(
        value: fakeProvider,
        child: const MaterialApp(home: MyTripsScreen()),
      ),
    );
    await tester.pump();

    expect(find.text('Kudlu Gate → Anekal'), findsOneWidget);
    expect(find.textContaining('Saved Bus: KA-BUS-007'), findsOneWidget);

    await tester.tap(find.text('Kudlu Gate → Anekal'));
    await tester.pumpAndSettle();

    expect(find.text('KA-BUS-007 • Journey Details'), findsOneWidget);
    expect(find.text('Singasandra'), findsOneWidget);
  });
}
