import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'journey_details_screen.dart';

class MyTripsScreen extends StatefulWidget {
  const MyTripsScreen({super.key});

  @override
  State<MyTripsScreen> createState() => _MyTripsScreenState();
}

class _MyTripsScreenState extends State<MyTripsScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (mounted) {
        Provider.of<TransitProvider>(context, listen: false).loadSavedTrips();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final savedTrips = provider.savedTrips;

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Trips', style: TextStyle(fontWeight: FontWeight.bold)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => provider.loadSavedTrips(),
          ),
        ],
      ),
      body: provider.isLoadingSavedTrips
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: () => provider.loadSavedTrips(),
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (provider.savedTripsError != null)
                    Card(
                      color: Colors.red.shade50,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(
                          'Could not load saved trips: ${provider.savedTripsError}',
                          style: const TextStyle(color: MoveSyncTheme.red),
                        ),
                      ),
                    )
                  else if (savedTrips.isEmpty)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(24),
                        child: Column(
                          children: [
                            Icon(Icons.route_outlined, size: 42, color: Colors.grey),
                            SizedBox(height: 8),
                            Text('No saved trips yet', style: TextStyle(fontWeight: FontWeight.bold)),
                            SizedBox(height: 4),
                            Text(
                              'Use the Explore tab to plan a journey and tap Save Trip to see matching buses here.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.grey, fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                    )
                  else
                    ...savedTrips.map((trip) {
                      final primaryJourney = trip.selectedJourney ??
                          (trip.matchingBuses.isNotEmpty ? trip.matchingBuses.first : null);
                      return Card(
                        margin: const EdgeInsets.only(bottom: 14),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(12),
                          onTap: primaryJourney != null
                              ? () {
                                  Navigator.push(
                                    context,
                                    MaterialPageRoute(builder: (_) => JourneyDetailsScreen(journey: primaryJourney)),
                                  );
                                }
                              : null,
                          child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  const Icon(Icons.bookmark, color: MoveSyncTheme.teal, size: 18),
                                  const SizedBox(width: 6),
                                  Expanded(
                                    child: Text(
                                      '${trip.sourceStop} → ${trip.destinationStop}',
                                      style: const TextStyle(
                                        fontSize: 15,
                                        fontWeight: FontWeight.bold,
                                        color: MoveSyncTheme.navy,
                                      ),
                                    ),
                                  ),
                                  if (primaryJourney != null)
                                    const Icon(Icons.chevron_right, color: MoveSyncTheme.teal),
                                ],
                              ),
                              if (trip.selectedBusId != null && trip.selectedBusId!.isNotEmpty) ...[
                                const SizedBox(height: 4),
                                Text(
                                  'Saved Bus: ${trip.selectedBusId}${trip.selectedTripId != null && trip.selectedTripId!.isNotEmpty ? " • Trip #${trip.selectedTripId}" : ""}',
                                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: MoveSyncTheme.teal),
                                ),
                              ],
                              if (trip.intermediateStops.isNotEmpty) ...[
                                const SizedBox(height: 6),
                                Text(
                                  'Intermediate stops (${trip.intermediateStops.length}): ${trip.intermediateStops.take(5).join(" → ")}${trip.intermediateStops.length > 5 ? "..." : ""}',
                                  style: const TextStyle(fontSize: 12, color: Colors.black54),
                                ),
                              ],
                              const Divider(height: 18),
                              if (!trip.valid || trip.matchingBuses.isEmpty)
                                Text(
                                  trip.message ?? 'No direct bus is available for this saved journey.',
                                  style: const TextStyle(fontSize: 13, color: MoveSyncTheme.amber),
                                )
                              else
                                ...trip.matchingBuses.take(5).map((busMatch) {
                                  final color = MoveSyncTheme.statusColor(
                                    busMatch.occupancyPct >= 100
                                        ? 'CRITICAL'
                                        : (busMatch.occupancyPct >= 75 ? 'WARNING' : 'NORMAL'),
                                  );
                                  return ListTile(
                                    contentPadding: EdgeInsets.zero,
                                    leading: CircleAvatar(
                                      backgroundColor: color.withValues(alpha: 0.14),
                                      child: Icon(Icons.directions_bus, color: color, size: 20),
                                    ),
                                    title: Text(
                                      '${busMatch.busId} • ${busMatch.crowdStatus}',
                                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                    ),
                                    subtitle: Text(
                                      'Departs ${busMatch.boardingStop} (${busMatch.boardingTime}) • '
                                      'Arrives ${busMatch.destinationStop} (${busMatch.destinationTime})\n'
                                      '${busMatch.currentOccupancy}/${busMatch.busCapacity} passengers (${busMatch.occupancyPct.toStringAsFixed(0)}%)',
                                      style: const TextStyle(fontSize: 12),
                                    ),
                                    isThreeLine: true,
                                    trailing: const Icon(Icons.chevron_right),
                                    onTap: () {
                                      Navigator.push(
                                        context,
                                        MaterialPageRoute(builder: (_) => JourneyDetailsScreen(journey: busMatch)),
                                      );
                                    },
                                  );
                                }),
                            ],
                          ),
                        ),
                        ),
                      );
                    }),
                ],
              ),
            ),
    );
  }
}
