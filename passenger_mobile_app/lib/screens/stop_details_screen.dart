import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/transit_models.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'tracking_screen.dart';

class StopDetailsScreen extends StatefulWidget {
  final NearbyStop stop;

  const StopDetailsScreen({super.key, required this.stop});

  @override
  State<StopDetailsScreen> createState() => _StopDetailsScreenState();
}

class _StopDetailsScreenState extends State<StopDetailsScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (mounted) {
        Provider.of<TransitProvider>(context, listen: false).loadStopDetails(widget.stop.stopId);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final details = provider.selectedStopDetails;
    final buses = details?.buses ?? [];

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.stop.stopName, style: const TextStyle(fontWeight: FontWeight.bold)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => provider.loadStopDetails(widget.stop.stopId),
          ),
        ],
      ),
      body: provider.isLoadingStopDetails
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: () => provider.loadStopDetails(widget.stop.stopId),
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Stop #${widget.stop.stopOrder} • ${widget.stop.stopName}',
                            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy),
                          ),
                          const SizedBox(height: 4),
                          const Text(
                            'Route: KR Market → Anekal (KR_MARKET_ANEKAL_VIA_ECITY)',
                            style: TextStyle(fontSize: 12, color: MoveSyncTheme.teal, fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            widget.stop.gpsAvailable && widget.stop.latitude != null
                                ? 'Surveyed GPS: ${widget.stop.latitude!.toStringAsFixed(4)}, ${widget.stop.longitude!.toStringAsFixed(4)}'
                                : 'Location: Simulated / Dataset stop sequence (GPS coordinates unavailable)',
                            style: const TextStyle(fontSize: 12, color: Colors.black54),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    'Buses Serving This Stop (${buses.length})',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy),
                  ),
                  const SizedBox(height: 8),
                  if (buses.isEmpty)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(20),
                        child: Center(child: Text('No buses found for this stop.', style: TextStyle(color: Colors.grey))),
                      ),
                    )
                  else
                    ...buses.map((b) {
                      final color = MoveSyncTheme.statusColor(
                        b.occupancyPct >= 95
                            ? 'CRITICAL'
                            : (b.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
                      );
                      return Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        child: ListTile(
                          leading: CircleAvatar(
                            backgroundColor: color.withValues(alpha: 0.14),
                            child: Icon(Icons.directions_bus, color: color),
                          ),
                          title: Text('${b.busId} • ${b.crowdStatus}', style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Text(
                            'Current (Sim): ${b.currentStopName} (#${b.currentStopSequence})\n'
                            'Next Stop: ${b.nextStopName ?? "Terminal"}\n'
                            '${b.currentOccupancy}/${b.busCapacity} passengers • ${b.availableSeats} seats free',
                            style: const TextStyle(fontSize: 12),
                          ),
                          isThreeLine: true,
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () async {
                            final busObj = provider.buses.where((x) => x.busId == b.busId).firstOrNull ??
                                BusState(
                                  busId: b.busId,
                                  plateNumber: 'KA-01-F-${b.busId.substring(b.busId.length - 3)}',
                                  capacity: b.busCapacity,
                                  currentOccupancy: b.currentOccupancy,
                                  occupancyPct: b.occupancyPct,
                                  occupancyStatus: b.occupancyPct >= 95
                                      ? 'CRITICAL'
                                      : (b.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
                                  currentRouteId: b.routeId,
                                  routeName: b.routeName,
                                  lastStopId: b.currentStopId,
                                  lastStopName: b.currentStopName,
                                  nextStopName: b.nextStopName,
                                  currentTripId: b.tripId,
                                  status: 'IN_SERVICE',
                                  isReliefBus: false,
                                  dataProvenance: 'SYNTHETIC_DATASET_SNAPSHOT',
                                );
                            await provider.selectBus(busObj);
                            if (context.mounted) {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => TrackingScreen(bus: busObj)),
                              );
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
