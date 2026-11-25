import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'route_details_screen.dart';

class ExploreScreen extends StatefulWidget {
  const ExploreScreen({super.key});

  @override
  State<ExploreScreen> createState() => _ExploreScreenState();
}

class _ExploreScreenState extends State<ExploreScreen> {
  final _searchController = TextEditingController();
  String? _selectedSource;
  String? _selectedDestination;

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

    final allStopNames = provider.stopSearchResults.map((s) => s.stopName).toSet().toList()..sort();

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
              hintText: 'Search bus stop or route (e.g. MG Road, R101)...',
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

          // Source & Destination Planner
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Plan Journey (Source & Destination)', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 10),
                  DropdownButtonFormField<String>(
                    value: _selectedSource,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'From (Starting Stop)', border: OutlineInputBorder(), isDense: true),
                    items: allStopNames.map((n) => DropdownMenuItem(value: n, child: Text(n, overflow: TextOverflow.ellipsis))).toList(),
                    onChanged: (v) => setState(() => _selectedSource = v),
                  ),
                  const SizedBox(height: 10),
                  DropdownButtonFormField<String>(
                    value: _selectedDestination,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'To (Destination Stop)', border: OutlineInputBorder(), isDense: true),
                    items: allStopNames.map((n) => DropdownMenuItem(value: n, child: Text(n, overflow: TextOverflow.ellipsis))).toList(),
                    onChanged: (v) => setState(() => _selectedDestination = v),
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: (_selectedSource != null && _selectedDestination != null)
                          ? () {
                              provider.setJourneyStops(_selectedSource!, _selectedDestination!);
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text('Journey saved: $_selectedSource → $_selectedDestination')),
                              );
                            }
                          : null,
                      child: const Text('Find Routes & Save Trip'),
                    ),
                  ),
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
