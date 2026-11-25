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
  String _selectedStopQuery = '';
  final TextEditingController _stopSearchController = TextEditingController();

  @override
  void dispose() {
    _stopSearchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final userName = provider.currentUser?.displayName ?? 'Commuter';

    final stopNames = <String>{
      ...provider.allStops.map((s) => s.stopName),
      ...provider.routes.expand((r) => r.stops.map((s) => s.stopName)),
    }.where((name) => name.trim().isNotEmpty).toList();

    final query = _selectedStopQuery.trim().toLowerCase();
    final matchingStop = query.isEmpty
        ? false
        : stopNames.any((s) => s.toLowerCase().contains(query));

    final filteredBuses = query.isEmpty
        ? provider.buses
        : provider.buses.where((b) {
            final idMatch = b.busId.toLowerCase().contains(query);
            final stopMatch = matchingStop && (b.currentRouteId == 'KR_MARKET_ANEKAL_VIA_ECITY' || provider.routes.any((r) => r.routeId == b.currentRouteId && r.stops.any((s) => s.stopName.toLowerCase().contains(query))));
            final currentStopMatch = (b.lastStopName ?? '').toLowerCase().contains(query);
            final nextStopMatch = (b.nextStopName ?? '').toLowerCase().contains(query);
            return idMatch || stopMatch || currentStopMatch || nextStopMatch;
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

                  // Searchable Bus Stop Name Autocomplete
                  Autocomplete<String>(
                    optionsBuilder: (TextEditingValue textEditingValue) {
                      final q = textEditingValue.text.trim().toLowerCase();
                      if (q.isEmpty) return stopNames;
                      return stopNames.where((s) => s.toLowerCase().contains(q));
                    },
                    onSelected: (String selection) {
                      setState(() {
                        _selectedStopQuery = selection;
                        _stopSearchController.text = selection;
                      });
                    },
                    fieldViewBuilder: (context, controller, focusNode, onFieldSubmitted) {
                      if (_stopSearchController.text.isNotEmpty && controller.text != _stopSearchController.text) {
                        controller.text = _stopSearchController.text;
                      }
                      return TextField(
                        controller: controller,
                        focusNode: focusNode,
                        onChanged: (val) {
                          _stopSearchController.text = val;
                          setState(() => _selectedStopQuery = val);
                        },
                        decoration: InputDecoration(
                          hintText: 'Search stop (KR Market, Madiwala) or bus ID (BUS-001)...',
                          prefixIcon: const Icon(Icons.search),
                          suffixIcon: _selectedStopQuery.isNotEmpty
                              ? IconButton(
                                  icon: const Icon(Icons.clear),
                                  onPressed: () {
                                    controller.clear();
                                    _stopSearchController.clear();
                                    setState(() => _selectedStopQuery = '');
                                  },
                                )
                              : null,
                          filled: true,
                          fillColor: Colors.white,
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      );
                    },
                  ),
                  if (_selectedStopQuery.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: [
                        Chip(
                          avatar: const Icon(Icons.place, size: 16, color: MoveSyncTheme.teal),
                          label: Text('Stop: $_selectedStopQuery'),
                          onDeleted: () {
                            _stopSearchController.clear();
                            setState(() => _selectedStopQuery = '');
                          },
                        ),
                      ],
                    ),
                  ],
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
                          title: Text('${bus.busId} • ${bus.routeName ?? "KR Market → Anekal"}',
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Current: ${bus.lastStopName ?? "In Transit"} • Next: ${bus.nextStopName ?? "Anekal"}',
                                style: const TextStyle(fontSize: 12),
                              ),
                              Text('${bus.currentOccupancy} / ${bus.capacity} passengers • ${bus.availableCapacity} seats available'),
                              const SizedBox(height: 2),
                              Text('$crowdLabel • ${bus.status}', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: statusColor)),
                            ],
                          ),
                          isThreeLine: true,
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
