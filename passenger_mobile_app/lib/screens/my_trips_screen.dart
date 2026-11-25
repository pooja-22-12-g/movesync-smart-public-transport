import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'route_details_screen.dart';

class MyTripsScreen extends StatelessWidget {
  const MyTripsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final hasJourney = provider.sourceStopQuery.isNotEmpty && provider.destinationStopQuery.isNotEmpty;

    return Scaffold(
      appBar: AppBar(title: const Text('My Trips', style: TextStyle(fontWeight: FontWeight.bold))),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (hasJourney)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Planned Journey', style: TextStyle(fontWeight: FontWeight.bold, color: MoveSyncTheme.teal)),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Icon(Icons.trip_origin, color: MoveSyncTheme.green, size: 18),
                        const SizedBox(width: 8),
                        Expanded(child: Text(provider.sourceStopQuery, style: const TextStyle(fontWeight: FontWeight.w600))),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        const Icon(Icons.place, color: MoveSyncTheme.red, size: 18),
                        const SizedBox(width: 8),
                        Expanded(child: Text(provider.destinationStopQuery, style: const TextStyle(fontWeight: FontWeight.w600))),
                      ],
                    ),
                  ],
                ),
              ),
            )
          else
            const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Column(
                  children: [
                    Icon(Icons.route_outlined, size: 42, color: Colors.grey),
                    SizedBox(height: 8),
                    Text('No saved journey yet', style: TextStyle(fontWeight: FontWeight.bold)),
                    SizedBox(height: 4),
                    Text('Use the Explore tab to choose your source and destination stops.', textAlign: TextAlign.center, style: TextStyle(color: Colors.grey, fontSize: 12)),
                  ],
                ),
              ),
            ),
          const SizedBox(height: 16),
          const Text('Available Transit Corridors', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
          const SizedBox(height: 8),
          ...provider.routes.map((r) => Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: const CircleAvatar(
                    backgroundColor: MoveSyncTheme.lightBlue,
                    child: Icon(Icons.directions_bus, color: MoveSyncTheme.navy),
                  ),
                  title: Text('Route ${r.routeId}', style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text('${r.totalStops} Stops • Cycle ~${r.baseCycleTimeMins} mins'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    provider.selectRoute(r);
                    Navigator.push(context, MaterialPageRoute(builder: (_) => RouteDetailsScreen(route: r)));
                  },
                ),
              )),
        ],
      ),
    );
  }
}
