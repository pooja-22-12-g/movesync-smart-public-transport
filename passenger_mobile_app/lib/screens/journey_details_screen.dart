import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/transit_models.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'tracking_screen.dart';

class JourneyDetailsScreen extends StatefulWidget {
  final JourneyOption journey;

  const JourneyDetailsScreen({super.key, required this.journey});

  @override
  State<JourneyDetailsScreen> createState() => _JourneyDetailsScreenState();
}

class _JourneyDetailsScreenState extends State<JourneyDetailsScreen> {
  bool _isSaving = false;

  Future<void> _saveTrip() async {
    if (_isSaving) return;
    setState(() => _isSaving = true);
    final j = widget.journey;
    final allStopsCount = j.intermediateStops.length + 2;
    final provider = Provider.of<TransitProvider>(context, listen: false);
    final res = await provider.saveTrip(
      j.boardingStop,
      j.destinationStop,
      sourceStopId: j.boardingStopId,
      destinationStopId: j.destinationStopId,
      busId: j.busId,
      tripId: j.tripId,
      boardingTime: j.boardingTime,
      destinationTime: j.destinationTime,
      intermediateStops: j.intermediateStops,
      totalStops: allStopsCount,
    );
    if (!mounted) return;
    setState(() => _isSaving = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          res['ok'] == true
              ? 'Saved trip: ${j.boardingStop} → ${j.destinationStop} (${j.busId})'
              : (res['message']?.toString() ?? 'Failed to save trip'),
        ),
        backgroundColor: res['ok'] == true ? MoveSyncTheme.green : MoveSyncTheme.red,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final j = widget.journey;
    final provider = Provider.of<TransitProvider>(context);
    final availableSeats = (j.busCapacity - j.currentOccupancy).clamp(0, j.busCapacity);
    final allStops = <String>[
      j.boardingStop,
      ...j.intermediateStops,
      j.destinationStop,
    ];
    final totalStops = allStops.length;
    final statusColor = MoveSyncTheme.statusColor(
      j.occupancyPct >= 95
          ? 'CRITICAL'
          : (j.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
    );

    return Scaffold(
      appBar: AppBar(
        title: Text('${j.busId} • Journey Details', style: const TextStyle(fontWeight: FontWeight.bold)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        j.busId,
                        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: statusColor.withValues(alpha: 0.14),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(
                          j.crowdStatus,
                          style: TextStyle(color: statusColor, fontWeight: FontWeight.bold, fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${j.boardingStop} → ${j.destinationStop}',
                    style: const TextStyle(fontSize: 14, color: MoveSyncTheme.teal, fontWeight: FontWeight.bold),
                  ),
                  Text(
                    'Corridor: ${j.corridorName} (${j.routeId}) • Trip #${j.tripId}',
                    style: const TextStyle(fontSize: 11, color: Colors.black54),
                  ),
                  const Divider(height: 20),
                  Row(
                    children: [
                      const Icon(Icons.trip_origin, color: MoveSyncTheme.green, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'From: ${j.boardingStop} (${j.boardingTime})',
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      const Icon(Icons.place, color: MoveSyncTheme.red, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'To: ${j.destinationStop} (${j.destinationTime})',
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _metric('Occupancy', '${j.currentOccupancy}/${j.busCapacity}', statusColor),
                      _metric('Available', '$availableSeats seats', MoveSyncTheme.teal),
                      _metric('Total Stops', '$totalStops', MoveSyncTheme.navy),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          icon: _isSaving
                              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                              : const Icon(Icons.bookmark_add_outlined),
                          label: Text(_isSaving ? 'Saving...' : 'Save Trip'),
                          onPressed: _isSaving ? null : _saveTrip,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: ElevatedButton.icon(
                          icon: const Icon(Icons.directions_bus),
                          label: const Text('Bus Details'),
                          onPressed: () async {
                            final bus = provider.buses.where((b) => b.busId == j.busId).firstOrNull ??
                                BusState(
                                  busId: j.busId,
                                  plateNumber: 'KA-01-F-${j.busId.substring(j.busId.length - 3)}',
                                  capacity: j.busCapacity,
                                  currentOccupancy: j.currentOccupancy,
                                  occupancyPct: j.occupancyPct,
                                  occupancyStatus: j.occupancyPct >= 95
                                      ? 'CRITICAL'
                                      : (j.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
                                  currentRouteId: j.routeId,
                                  routeName: '${j.boardingStop} → ${j.destinationStop}',
                                  lastStopId: j.boardingStopId,
                                  lastStopName: j.boardingStop,
                                  currentTripId: j.tripId,
                                  status: 'IN_SERVICE',
                                  isReliefBus: false,
                                  dataProvenance: j.dataProvenance,
                                );
                            await provider.selectBus(bus, journey: j);
                            if (context.mounted) {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => TrackingScreen(bus: bus)),
                              );
                            }
                          },
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Complete Stop Sequence ($totalStops Stops)',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy),
          ),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                children: List.generate(allStops.length, (index) {
                  final isFirst = index == 0;
                  final isLast = index == allStops.length - 1;
                  final stopSeq = j.boardingSequence + index;
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Column(
                        children: [
                          CircleAvatar(
                            radius: 13,
                            backgroundColor: isFirst
                                ? MoveSyncTheme.green
                                : (isLast ? MoveSyncTheme.red : MoveSyncTheme.navy),
                            child: Text(
                              '$stopSeq',
                              style: const TextStyle(color: Colors.white, fontSize: 10),
                            ),
                          ),
                          if (!isLast)
                            Container(width: 2, height: 24, color: Colors.grey.shade300),
                        ],
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            allStops[index],
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: (isFirst || isLast) ? FontWeight.bold : FontWeight.w500,
                              color: (isFirst || isLast) ? MoveSyncTheme.navy : Colors.black87,
                            ),
                          ),
                        ),
                      ),
                    ],
                  );
                }),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _metric(String label, String value, Color color) {
    return Column(
      children: [
        Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: color)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.black54)),
      ],
    );
  }
}
