import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../models/transit_models.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';

class TrackingScreen extends StatefulWidget {
  final BusState? bus;

  const TrackingScreen({super.key, this.bus});

  @override
  State<TrackingScreen> createState() => _TrackingScreenState();
}

class _TrackingScreenState extends State<TrackingScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (!mounted) return;
      final provider = Provider.of<TransitProvider>(context, listen: false);
      final target = widget.bus ?? provider.selectedBus ?? (provider.buses.isNotEmpty ? provider.buses.first : null);
      if (target != null && provider.busUpcomingResponse?.busId != target.busId) {
        provider.selectBus(target);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final activeBus = widget.bus ?? provider.selectedBus ?? (provider.buses.isNotEmpty ? provider.buses.first : null);

    if (activeBus == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Live Bus Tracking', style: TextStyle(fontWeight: FontWeight.bold))),
        body: const Center(child: Text('No active buses available to track right now.')),
      );
    }

    final location = provider.selectedBusLocation;
    final forecasts = provider.currentForecasts;
    final upcomingResp = (provider.busUpcomingResponse?.busId == activeBus.busId)
        ? provider.busUpcomingResponse
        : null;
    final alternatives = provider.getAlternativeBuses(activeBus.currentRouteId ?? '', activeBus.busId);

    final busLatLng = location != null
        ? LatLng(location.latitude, location.longitude)
        : const LatLng(12.9770, 77.5713);

    final statusColor = MoveSyncTheme.statusColor(activeBus.occupancyStatus);
    final crowdLabel = upcomingResp?.crowdStatus ??
        MoveSyncTheme.passengerCrowdLabel(activeBus.currentOccupancy, activeBus.capacity);
    final isSimulatedLoc = location == null ||
        location.dataProvenance.contains('SIMULATED') ||
        location.dataProvenance.contains('INTERPOLATED') ||
        location.dataProvenance.contains('DATASET');

    return Scaffold(
      appBar: AppBar(
        title: Text('Live Tracking • ${activeBus.busId}', style: const TextStyle(fontWeight: FontWeight.bold)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh Occupancy & Predictions',
            onPressed: () => provider.selectBus(activeBus),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => provider.selectBus(activeBus),
        child: ListView(
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
                                    Text(
                                      'Route ${activeBus.currentRouteId ?? "Depot"} • ${isSimulatedLoc ? "Dataset / Simulated Location" : "Live GPS"}',
                                      style: const TextStyle(fontSize: 12, color: Colors.black54),
                                    ),
                                    if (upcomingResp != null)
                                      Text(
                                        'Current Stop: ${upcomingResp.currentStopName} (#${upcomingResp.currentStopSequence})',
                                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: MoveSyncTheme.teal),
                                      ),
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
                                _stat('Current (Sim)', '${activeBus.currentOccupancy} / ${activeBus.capacity}', statusColor),
                                _stat('Occupied', '${activeBus.occupancyPct.toStringAsFixed(0)}%', MoveSyncTheme.teal),
                                _stat('Available', '${activeBus.availableCapacity} seats', MoveSyncTheme.navy),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                              decoration: BoxDecoration(
                                color: Colors.grey.shade100,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                upcomingResp?.actualOccupancyAvailable == true
                                    ? 'Actual Occupancy (Live Sensor): ${upcomingResp!.actualOccupancy} / ${activeBus.capacity}'
                                    : 'Actual Occupancy: Not available (measured only by live sensor)${upcomingResp != null && upcomingResp.tripId.isNotEmpty ? " • Trip #${upcomingResp.tripId}" : ""}',
                                style: const TextStyle(fontSize: 11, color: Colors.black54),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Upcoming Stops & ML Occupancy Prediction in Route Sequence
                const Text('Occupancy Prediction & Upcoming Stops', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                const SizedBox(height: 2),
                const Text(
                  'Expected occupancy predicted by Random Forest ML model along the 50-stop route.',
                  style: TextStyle(fontSize: 11, color: Colors.black54),
                ),
                const SizedBox(height: 8),
                if (provider.isLoadingUpcoming)
                  const Center(child: Padding(padding: EdgeInsets.all(16), child: CircularProgressIndicator()))
                else if (upcomingResp != null && upcomingResp.upcomingStops.isNotEmpty)
                  ...upcomingResp.upcomingStops.map((s) {
                    final sColor = MoveSyncTheme.statusColor(
                      s.occupancyPct >= 95
                          ? 'CRITICAL'
                          : (s.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
                    );
                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      shape: s.isNextStop
                          ? RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                              side: const BorderSide(color: MoveSyncTheme.teal, width: 1.5),
                            )
                          : null,
                      child: ListTile(
                        leading: CircleAvatar(
                          radius: 16,
                          backgroundColor: s.isNextStop ? MoveSyncTheme.teal : MoveSyncTheme.navy,
                          child: Text('#${s.stopSequence}', style: const TextStyle(color: Colors.white, fontSize: 11)),
                        ),
                        title: Row(
                          children: [
                            Expanded(
                              child: Text(s.stopName, style: const TextStyle(fontWeight: FontWeight.w600)),
                            ),
                            if (s.isNextStop)
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: MoveSyncTheme.teal.withValues(alpha: 0.14),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: const Text(
                                  'NEXT STOP',
                                  style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: MoveSyncTheme.teal),
                                ),
                              ),
                          ],
                        ),
                        subtitle: Text(
                          s.predictionAvailable
                              ? 'Expected (ML): ${s.expectedOccupancy} / ${s.busCapacity} (${s.occupancyPct.toStringAsFixed(0)}%) • '
                                '${s.availableSeats} seats free\n'
                                'Board +${s.expectedBoarding} / Alight -${s.expectedAlighting}'
                                '${s.expectedTime.isNotEmpty ? " • ${s.expectedTime}" : ""}'
                              : 'Prediction not available for this stop\n'
                                'Board +${s.expectedBoarding} / Alight -${s.expectedAlighting}'
                                '${s.expectedTime.isNotEmpty ? " • ${s.expectedTime}" : ""}',
                          style: const TextStyle(fontSize: 12),
                        ),
                        isThreeLine: true,
                        trailing: Text(
                          s.predictionAvailable ? s.crowdStatus : 'N/A',
                          style: TextStyle(fontWeight: FontWeight.bold, color: sColor, fontSize: 12),
                        ),
                      ),
                    );
                  })
                else if (forecasts.isEmpty)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Text(
                        upcomingResp?.message ?? 'Prediction not available for the selected bus and trip.',
                        style: const TextStyle(color: Colors.black54),
                      ),
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
                if (upcomingResp != null && upcomingResp.lessCrowdedAlternatives.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  const Text('Less-Crowded Alternative Buses', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                  const SizedBox(height: 8),
                  ...upcomingResp.lessCrowdedAlternatives.map((alt) {
                    final altColor = MoveSyncTheme.statusColor(
                      alt.occupancyPct >= 100
                          ? 'CRITICAL'
                          : (alt.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
                    );
                    return Card(
                      color: Colors.green.shade50,
                      margin: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        leading: Icon(Icons.directions_bus, color: altColor),
                        title: Text(alt.busId, style: const TextStyle(fontWeight: FontWeight.bold)),
                        subtitle: Text('At ${alt.currentStop} • ${alt.crowdStatus} (${alt.occupancyPct.toStringAsFixed(0)}%)'),
                        trailing: Text('${alt.currentOccupancy}/${alt.busCapacity}', style: TextStyle(fontWeight: FontWeight.bold, color: altColor)),
                      ),
                    );
                  }),
                ] else if (alternatives.isNotEmpty) ...[
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
