import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'tracking_screen.dart';
import 'route_details_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _searchQuery = '';

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final userName = provider.currentUser?.displayName ?? 'Commuter';

    final filteredBuses = provider.buses.where((b) {
      final idMatch = b.busId.toLowerCase().contains(_searchQuery.toLowerCase());
      final routeMatch = (b.currentRouteId ?? '').toLowerCase().contains(_searchQuery.toLowerCase());
      return idMatch || routeMatch;
    }).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('MoveSync', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 19)),
            Text('Smart Mobility. Better Journeys.', style: TextStyle(fontSize: 11, color: Colors.white70)),
          ],
        ),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: () => provider.refreshData()),
        ],
      ),
      body: provider.isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: () => provider.refreshData(),
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Text('Hello, $userName', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      const Icon(Icons.location_on_outlined, size: 15, color: MoveSyncTheme.teal),
                      const SizedBox(width: 4),
                      Expanded(child: Text(provider.locationStatus, style: const TextStyle(fontSize: 12, color: Colors.black54))),
                      TextButton(
                        onPressed: () => provider.detectPassengerLocation(),
                        child: const Text('Update GPS', style: TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),

                  // Search Bar
                  TextField(
                    onChanged: (val) => setState(() => _searchQuery = val),
                    decoration: InputDecoration(
                      hintText: 'Search bus number (KA-BUS-001) or route (R101)...',
                      prefixIcon: const Icon(Icons.search),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                    ),
                  ),
                  const SizedBox(height: 14),

                  // Travel Alerts
                  if (provider.alerts.isNotEmpty) ...[
                    ...provider.alerts.take(2).map((alert) {
                      final isCrit = alert.alertLevel == 'CRITICAL';
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: isCrit ? Colors.red.shade50 : Colors.amber.shade50,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: isCrit ? MoveSyncTheme.red : MoveSyncTheme.amber),
                        ),
                        child: Row(
                          children: [
                            Icon(Icons.info_outline, color: isCrit ? MoveSyncTheme.red : MoveSyncTheme.amber),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                'Route ${alert.routeId}: Bus ${alert.busId} is ${MoveSyncTheme.passengerCrowdLabel(alert.currentOccupancy, alert.capacity).toLowerCase()} (${alert.currentOccupancy}/${alert.capacity}).',
                                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                              ),
                            ),
                          ],
                        ),
                      );
                    }),
                    const SizedBox(height: 10),
                  ],

                  // Routes Carousel
                  const Text('Routes', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                  const SizedBox(height: 8),
                  SizedBox(
                    height: 76,
                    child: ListView.builder(
                      scrollDirection: Axis.horizontal,
                      itemCount: provider.routes.length,
                      itemBuilder: (ctx, i) {
                        final r = provider.routes[i];
                        return GestureDetector(
                          onTap: () {
                            provider.selectRoute(r);
                            Navigator.push(context, MaterialPageRoute(builder: (_) => RouteDetailsScreen(route: r)));
                          },
                          child: Container(
                            width: 130,
                            margin: const EdgeInsets.only(right: 10),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: Colors.grey.shade200),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(r.routeId, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                                Text('${r.totalStops} Stops', style: const TextStyle(fontSize: 12, color: Colors.black54)),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 18),

                  // Available Buses
                  Text('Available Buses (${filteredBuses.length})',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                  const SizedBox(height: 8),
                  if (filteredBuses.isEmpty)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(24),
                        child: Center(child: Text('No buses matching your search.', style: TextStyle(color: Colors.grey))),
                      ),
                    )
                  else
                    ...filteredBuses.map((bus) {
                      final statusColor = MoveSyncTheme.statusColor(bus.occupancyStatus);
                      final crowdLabel = MoveSyncTheme.passengerCrowdLabel(bus.currentOccupancy, bus.capacity);

                      return Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                          leading: CircleAvatar(
                            backgroundColor: statusColor.withValues(alpha: 0.14),
                            child: Icon(Icons.directions_bus, color: statusColor),
                          ),
                          title: Text('${bus.busId} • Route ${bus.currentRouteId ?? "Depot"}',
                              style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('${bus.currentOccupancy} / ${bus.capacity} passengers • ${bus.availableCapacity} seats available'),
                              const SizedBox(height: 4),
                              Text(crowdLabel, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: statusColor)),
                            ],
                          ),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () async {
                            await provider.selectBus(bus);
                            if (context.mounted) {
                              Navigator.push(context, MaterialPageRoute(builder: (_) => TrackingScreen(bus: bus)));
                            }
                          },
                        ),
                      );
                    }),
                ],
              ),
            ),
    );
  }
}
