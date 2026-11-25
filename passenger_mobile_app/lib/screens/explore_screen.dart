import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'route_details_screen.dart';
import 'tracking_screen.dart';

class ExploreScreen extends StatefulWidget {
  const ExploreScreen({super.key});

  @override
  State<ExploreScreen> createState() => _ExploreScreenState();
}

class _ExploreScreenState extends State<ExploreScreen> {
  final _searchController = TextEditingController();
  final _sourceController = TextEditingController();
  final _destinationController = TextEditingController();
  String _sourceText = '';
  String _destinationText = '';

  @override
  void dispose() {
    _searchController.dispose();
    _sourceController.dispose();
    _destinationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final stopsToDisplay = provider.nearbyStops.isNotEmpty ? provider.nearbyStops : provider.stopSearchResults;

    final mapCenter = (provider.passengerLat != null && provider.passengerLon != null)
        ? LatLng(provider.passengerLat!, provider.passengerLon!)
        : const LatLng(12.9716, 77.5946);

    final markers = <Marker>[
      if (provider.passengerLat != null && provider.passengerLon != null)
        Marker(
          point: LatLng(provider.passengerLat!, provider.passengerLon!),
          width: 36,
          height: 36,
          child: const CircleAvatar(
            backgroundColor: MoveSyncTheme.teal,
            child: Icon(Icons.my_location, color: Colors.white, size: 18),
          ),
        ),
      ...stopsToDisplay.take(15).map(
            (s) => Marker(
              point: LatLng(s.latitude, s.longitude),
              width: 32,
              height: 32,
              child: const CircleAvatar(
                backgroundColor: MoveSyncTheme.navy,
                child: Icon(Icons.place, color: Colors.white, size: 16),
              ),
            ),
          ),
    ];

    final allStopNames = <String>{
      ...provider.allStops.map((s) => s.stopName),
      ...provider.routes.expand((r) => r.stops.map((s) => s.stopName)),
    }.where((n) => n.trim().isNotEmpty).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Explore & Nearby Stops', style: TextStyle(fontWeight: FontWeight.bold)),
        actions: [
          IconButton(
            icon: const Icon(Icons.my_location),
            tooltip: 'Detect My Location',
            onPressed: () => provider.detectPassengerLocation(),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Location status & detect button
          Card(
            child: ListTile(
              leading: Icon(
                provider.locationPermissionDenied ? Icons.location_off : Icons.gps_fixed,
                color: provider.locationPermissionDenied ? MoveSyncTheme.amber : MoveSyncTheme.teal,
              ),
              title: const Text('Passenger Location', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
              subtitle: Text(provider.locationStatus, style: const TextStyle(fontSize: 12)),
              trailing: TextButton(
                onPressed: () => provider.detectPassengerLocation(),
                child: const Text('Detect'),
              ),
            ),
          ),
          const SizedBox(height: 12),

          // Manual Stop Search
          TextField(
            controller: _searchController,
            onChanged: (q) => provider.searchStops(q),
            decoration: InputDecoration(
              hintText: 'Search stop name (e.g. KR Market, Madiwala, Electronic City)...',
              prefixIcon: const Icon(Icons.search),
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
            ),
          ),
          const SizedBox(height: 12),

          // Map showing passenger & nearby stops
          Card(
            clipBehavior: Clip.antiAlias,
            child: SizedBox(
              height: 190,
              child: FlutterMap(
                options: MapOptions(initialCenter: mapCenter, initialZoom: 12.2),
                children: [
                  TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.example.passenger_mobile_app',
                  ),
                  MarkerLayer(markers: markers),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),

          // Source & Destination Planner (Searchable Autocomplete)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Plan Your Journey',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: MoveSyncTheme.navy),
                  ),
                  const SizedBox(height: 10),
                  Autocomplete<String>(
                    optionsBuilder: (TextEditingValue val) {
                      final q = val.text.trim().toLowerCase();
                      if (q.isEmpty) return allStopNames;
                      return allStopNames.where((s) => s.toLowerCase().contains(q));
                    },
                    onSelected: (selection) {
                      _sourceController.text = selection;
                      setState(() => _sourceText = selection);
                    },
                    fieldViewBuilder: (context, controller, focusNode, _) {
                      if (_sourceController.text.isNotEmpty && controller.text != _sourceController.text) {
                        controller.text = _sourceController.text;
                      }
                      return TextField(
                        controller: controller,
                        focusNode: focusNode,
                        onChanged: (v) {
                          _sourceController.text = v;
                          setState(() => _sourceText = v);
                        },
                        decoration: const InputDecoration(
                          labelText: 'Starting Point',
                          hintText: 'e.g. KR Market, Madiwala, Electronic City',
                          prefixIcon: Icon(Icons.trip_origin, color: MoveSyncTheme.green),
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                      );
                    },
                  ),
                  const SizedBox(height: 10),
                  Autocomplete<String>(
                    optionsBuilder: (TextEditingValue val) {
                      final q = val.text.trim().toLowerCase();
                      if (q.isEmpty) return allStopNames;
                      return allStopNames.where((s) => s.toLowerCase().contains(q));
                    },
                    onSelected: (selection) {
                      _destinationController.text = selection;
                      setState(() => _destinationText = selection);
                    },
                    fieldViewBuilder: (context, controller, focusNode, _) {
                      if (_destinationController.text.isNotEmpty && controller.text != _destinationController.text) {
                        controller.text = _destinationController.text;
                      }
                      return TextField(
                        controller: controller,
                        focusNode: focusNode,
                        onChanged: (v) {
                          _destinationController.text = v;
                          setState(() => _destinationText = v);
                        },
                        decoration: const InputDecoration(
                          labelText: 'Destination Point',
                          hintText: 'e.g. Anekal, Chandapura, Electronic City',
                          prefixIcon: Icon(Icons.place, color: MoveSyncTheme.red),
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton.icon(
                          icon: const Icon(Icons.search, size: 18),
                          label: const Text('Find Buses'),
                          onPressed: (_sourceText.trim().isNotEmpty &&
                                  _destinationText.trim().isNotEmpty &&
                                  !provider.isSearchingJourneys)
                              ? () => provider.searchJourneys(_sourceText.trim(), _destinationText.trim())
                              : null,
                        ),
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.bookmark_add_outlined, size: 18),
                        label: const Text('Save Trip'),
                        onPressed: (_sourceText.trim().isNotEmpty && _destinationText.trim().isNotEmpty)
                            ? () async {
                                final res = await provider.saveTrip(_sourceText.trim(), _destinationText.trim());
                                if (context.mounted) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        res['ok'] == true
                                            ? 'Saved trip: ${_sourceText.trim()} → ${_destinationText.trim()}'
                                            : (res['message']?.toString() ?? 'Could not save trip'),
                                      ),
                                    ),
                                  );
                                }
                              }
                            : null,
                      ),
                    ],
                  ),
                  if (provider.isSearchingJourneys) ...[
                    const SizedBox(height: 12),
                    const Center(child: CircularProgressIndicator()),
                  ] else if (provider.journeySearchResult != null) ...[
                    const SizedBox(height: 14),
                    Builder(
                      builder: (context) {
                        final res = provider.journeySearchResult!;
                        if (!res.valid || res.journeys.isEmpty) {
                          return Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.amber.shade50,
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(color: MoveSyncTheme.amber),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.info_outline, color: MoveSyncTheme.amber),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    res.message ?? 'No direct bus is available for this journey.',
                                    style: const TextStyle(fontSize: 13),
                                  ),
                                ),
                              ],
                            ),
                          );
                        }
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${res.sourceStop} → ${res.destinationStop} (${res.count} buses)',
                              style: const TextStyle(fontWeight: FontWeight.bold, color: MoveSyncTheme.teal),
                            ),
                            if (res.intermediateStops.isNotEmpty) ...[
                              const SizedBox(height: 4),
                              Text(
                                'Via ${res.intermediateStops.length} stops: ${res.intermediateStops.take(4).join(", ")}${res.intermediateStops.length > 4 ? "..." : ""}',
                                style: const TextStyle(fontSize: 12, color: Colors.black54),
                              ),
                            ],
                            const SizedBox(height: 8),
                            ...res.journeys.take(10).map((j) {
                              final color = MoveSyncTheme.statusColor(
                                j.occupancyPct >= 100
                                    ? 'CRITICAL'
                                    : (j.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
                              );
                              return Card(
                                margin: const EdgeInsets.only(bottom: 8),
                                color: Colors.grey.shade50,
                                child: ListTile(
                                  leading: CircleAvatar(
                                    backgroundColor: color.withValues(alpha: 0.14),
                                    child: Icon(Icons.directions_bus, color: color, size: 20),
                                  ),
                                  title: Text('${j.busId} • ${j.crowdStatus}',
                                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                                  subtitle: Text(
                                    'Board ${j.boardingTime} → Drop ${j.destinationTime}\n'
                                    '${j.currentOccupancy}/${j.busCapacity} passengers (${j.occupancyPct.toStringAsFixed(0)}%)',
                                    style: const TextStyle(fontSize: 12),
                                  ),
                                  isThreeLine: true,
                                  trailing: const Icon(Icons.chevron_right),
                                  onTap: () async {
                                    final bus = provider.buses.where((b) => b.busId == j.busId).firstOrNull;
                                    if (bus != null) {
                                      await provider.selectBus(bus);
                                      if (context.mounted) {
                                        Navigator.push(
                                          context,
                                          MaterialPageRoute(builder: (_) => TrackingScreen(bus: bus)),
                                        );
                                      }
                                    }
                                  },
                                ),
                              );
                            }),
                          ],
                        );
                      },
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          Text(
            provider.nearbyStops.isNotEmpty
                ? 'Nearby Bus Stops (${provider.nearbyStops.length})'
                : 'Available Surveyed Stops (${stopsToDisplay.length})',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy),
          ),
          const SizedBox(height: 8),
          if (stopsToDisplay.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Center(child: Text('No stops match your search.', style: TextStyle(color: Colors.grey))),
              ),
            )
          else
            ...stopsToDisplay.take(15).map((stop) {
              final etaText = stop.nextArrivalMins != null ? ' • Next bus ~${stop.nextArrivalMins} min (Simulated)' : '';
              final distText = stop.distanceKm != null ? '${stop.distanceKm} km away' : 'Surveyed Stop';
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: const CircleAvatar(
                    backgroundColor: MoveSyncTheme.lightBlue,
                    child: Icon(Icons.directions_bus_outlined, color: MoveSyncTheme.navy),
                  ),
                  title: Text(stop.stopName, style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text('$distText • Routes: ${stop.routes.join(", ")}$etaText'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    final routeId = stop.routes.isNotEmpty ? stop.routes.first : null;
                    final route = provider.routes.where((r) => r.routeId == routeId).firstOrNull;
                    if (route != null) {
                      provider.selectRoute(route);
                      Navigator.push(context, MaterialPageRoute(builder: (_) => RouteDetailsScreen(route: route)));
                    }
                  },
                ),
              );
            }),
        ],
      ),
    );
  }
}
