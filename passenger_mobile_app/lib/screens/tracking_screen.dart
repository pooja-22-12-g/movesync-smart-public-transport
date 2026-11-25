import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../models/transit_models.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';

class TrackingScreen extends StatelessWidget {
  final BusState? bus;

  const TrackingScreen({super.key, this.bus});

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final activeBus = bus ?? provider.selectedBus ?? (provider.buses.isNotEmpty ? provider.buses.first : null);

    if (activeBus == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Live Bus Tracking', style: TextStyle(fontWeight: FontWeight.bold))),
        body: const Center(child: Text('No active buses available to track right now.')),
      );
    }

    final location = provider.selectedBusLocation;
    final forecasts = provider.currentForecasts;
    final alternatives = provider.getAlternativeBuses(activeBus.currentRouteId ?? '', activeBus.busId);

    final busLatLng = location != null
        ? LatLng(location.latitude, location.longitude)
        : const LatLng(12.9770, 77.5713);

    final statusColor = MoveSyncTheme.statusColor(activeBus.occupancyStatus);
    final crowdLabel = MoveSyncTheme.passengerCrowdLabel(activeBus.currentOccupancy, activeBus.capacity);
    final isSimulatedLoc = location == null || location.dataProvenance.contains('SIMULATED') || location.dataProvenance.contains('INTERPOLATED');

    return Scaffold(
      appBar: AppBar(
        title: Text('Live Tracking • ${activeBus.busId}', style: const TextStyle(fontWeight: FontWeight.bold)),
      ),
      body: ListView(
        children: [
          // Map View
          SizedBox(
            height: 240,
            child: FlutterMap(
              options: MapOptions(initialCenter: busLatLng, initialZoom: 13.5),
              children: [
                TileLayer(
                  urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName: 'com.example.passenger_mobile_app',
                ),
                MarkerLayer(
                  markers: [
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
                    Marker(
                      point: busLatLng,
                      width: 44,
                      height: 44,
                      child: Container(
                        decoration: BoxDecoration(
                          color: statusColor,
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 3),
                        ),
                        child: const Icon(Icons.directions_bus, color: Colors.white, size: 22),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Bus photo header + provenance chip
                Card(
                  clipBehavior: Clip.antiAlias,
                  child: Column(
                    children: [
                      SizedBox(
                        height: 110,
                        width: double.infinity,
                        child: Image.asset(
                          'assets/images/city_bus_detail.jpg',
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                            color: MoveSyncTheme.lightBlue,
                            child: const Icon(Icons.directions_bus, size: 42, color: MoveSyncTheme.navy),
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(activeBus.busId, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                                    Text('Route ${activeBus.currentRouteId ?? "Depot"} • ${isSimulatedLoc ? "Simulated GPS Waypoint" : "Live GPS"}',
                                        style: const TextStyle(fontSize: 12, color: Colors.black54)),
                                  ],
                                ),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                                  decoration: BoxDecoration(
                                    color: statusColor.withValues(alpha: 0.14),
                                    borderRadius: BorderRadius.circular(20),
                                  ),
                                  child: Text(crowdLabel, style: TextStyle(color: statusColor, fontWeight: FontWeight.bold, fontSize: 12)),
                                ),
                              ],
                            ),
                            const SizedBox(height: 14),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceAround,
                              children: [
                                _stat('Occupancy', '${activeBus.currentOccupancy} / ${activeBus.capacity}', statusColor),
                                _stat('Available', '${activeBus.availableCapacity} seats', MoveSyncTheme.teal),
                                _stat('ETA', location?.estimatedArrivalMins != null ? '~${location!.estimatedArrivalMins} min' : 'N/A', MoveSyncTheme.navy),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Upcoming Stop Crowd Predictions (Plain Language)
                const Text('Upcoming Stops Crowd Outlook', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                const SizedBox(height: 8),
                if (forecasts.isEmpty)
                  const Card(
                    child: Padding(
                      padding: EdgeInsets.all(14),
                      child: Text('Upcoming stop forecasts will appear once the bus reaches its next scheduled stop.', style: TextStyle(color: Colors.black54)),
                    ),
                  )
                else
                  ...forecasts.map((f) {
                    final fColor = MoveSyncTheme.statusColor(f.predictedStatus);
                    final label = MoveSyncTheme.passengerCrowdLabel(f.predictedOccupancyRounded, activeBus.capacity);
                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        leading: CircleAvatar(
                          radius: 15,
                          backgroundColor: MoveSyncTheme.navy,
                          child: Text('+${f.stepAhead}', style: const TextStyle(color: Colors.white, fontSize: 11)),
                        ),
                        title: Text(f.targetStopName, style: const TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: Text('Predicted: ${f.predictedOccupancyRounded} passengers'),
                        trailing: Text(label, style: TextStyle(fontWeight: FontWeight.bold, color: fColor, fontSize: 12)),
                      ),
                    );
                  }),

                // Less-Crowded Alternatives
                if (alternatives.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  const Text('Less-Crowded Alternative Buses', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                  const SizedBox(height: 8),
                  ...alternatives.take(2).map((alt) {
                    final altColor = MoveSyncTheme.statusColor(alt.occupancyStatus);
                    return Card(
                      color: Colors.green.shade50,
                      margin: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        leading: Icon(Icons.directions_bus, color: altColor),
                        title: Text(alt.busId, style: const TextStyle(fontWeight: FontWeight.bold)),
                        subtitle: Text('${alt.availableCapacity} seats available • ${MoveSyncTheme.passengerCrowdLabel(alt.currentOccupancy, alt.capacity)}'),
                        trailing: Text('${alt.currentOccupancy}/${alt.capacity}', style: TextStyle(fontWeight: FontWeight.bold, color: altColor)),
                      ),
                    );
                  }),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _stat(String label, String value, Color color) {
    return Column(
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.black54)),
        const SizedBox(height: 3),
        Text(value, style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: color)),
      ],
    );
  }
}
