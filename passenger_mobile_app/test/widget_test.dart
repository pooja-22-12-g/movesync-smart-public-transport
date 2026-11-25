import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:passenger_mobile_app/main.dart';
import 'package:passenger_mobile_app/providers/transit_provider.dart';

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

    // Verify MoveSync branding on unified login screen
    expect(find.text('MoveSync'), findsOneWidget);
    expect(find.text('Smart Mobility. Better Journeys.'), findsOneWidget);
  });
}
