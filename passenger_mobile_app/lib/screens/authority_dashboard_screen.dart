import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';
import 'tracking_screen.dart';
import 'settings_screen.dart';

class AuthorityDashboardScreen extends StatefulWidget {
  const AuthorityDashboardScreen({super.key});

  @override
  State<AuthorityDashboardScreen> createState() => _AuthorityDashboardScreenState();
}

class _AuthorityDashboardScreenState extends State<AuthorityDashboardScreen> {
  int _tabIndex = 0;

  void _showCountingDialog(TransitProvider provider) {
    final busCtrl = TextEditingController(text: 'KA-BUS-001');
    final routeCtrl = TextEditingController(text: 'R047');
    final sessionCtrl = TextEditingController(text: 'VID_${DateTime.now().millisecondsSinceEpoch}');
    final boardCtrl = TextEditingController(text: '4');
    final alightCtrl = TextEditingController(text: '6');

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Record Video Counting Session'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: busCtrl, decoration: const InputDecoration(labelText: 'Bus ID')),
              TextField(controller: routeCtrl, decoration: const InputDecoration(labelText: 'Route ID')),
              TextField(controller: sessionCtrl, decoration: const InputDecoration(labelText: 'Session ID')),
              TextField(controller: boardCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Boarding Count')),
              TextField(controller: alightCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Alighting Count')),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () async {
              Navigator.pop(ctx);
              final res = await provider.submitCountingSession(
                busId: busCtrl.text.trim(),
                routeId: routeCtrl.text.trim(),
                sessionId: sessionCtrl.text.trim(),
                boardingCount: int.tryParse(boardCtrl.text) ?? 0,
                alightingCount: int.tryParse(alightCtrl.text) ?? 0,
              );
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(res['message']?.toString() ?? 'Session processed')),
                );
              }
            },
            child: const Text('Submit Session'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);

    final pages = [
      _buildFleetTab(provider),
      _buildAlertsTab(provider),
      _buildDispatchTab(provider),
      _buildFuelTab(provider),
      const SettingsScreen(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('MoveSync Authority', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
            Text('Smart Mobility. Better Journeys.', style: TextStyle(fontSize: 11, color: Colors.white70)),
          ],
        ),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: () => provider.refreshData()),
        ],
      ),
      body: provider.isLoading ? const Center(child: CircularProgressIndicator()) : pages[_tabIndex],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        onDestinationSelected: (i) => setState(() => _tabIndex = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.directions_bus_outlined), selectedIcon: Icon(Icons.directions_bus), label: 'Fleet'),
          NavigationDestination(icon: Icon(Icons.warning_amber_outlined), selectedIcon: Icon(Icons.warning_amber), label: 'Alerts'),
          NavigationDestination(icon: Icon(Icons.schedule_outlined), selectedIcon: Icon(Icons.schedule), label: 'Dispatch'),
          NavigationDestination(icon: Icon(Icons.local_gas_station_outlined), selectedIcon: Icon(Icons.local_gas_station), label: 'Fuel'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Account'),
        ],
      ),
    );
  }

  // ── 1. FLEET TAB ───────────────────────────────────────────────────────────
  Widget _buildFleetTab(TransitProvider provider) {
    final activeBuses = provider.buses.where((b) => b.status == 'IN_SERVICE').length;
    final criticalBuses = provider.buses.where((b) => b.occupancyStatus == 'CRITICAL').length;
    final cv = provider.cvSummary;

    final markers = provider.buses
        .where((b) => provider.allBusLocations.containsKey(b.busId))
        .map((b) {
          final loc = provider.allBusLocations[b.busId]!;
          final color = MoveSyncTheme.statusColor(b.occupancyStatus);
          return Marker(
            point: LatLng(loc.latitude, loc.longitude),
            width: 36,
            height: 36,
            child: Container(
              decoration: BoxDecoration(color: color, shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 2)),
              child: const Icon(Icons.directions_bus, color: Colors.white, size: 17),
            ),
          );
        })
        .toList();

    return RefreshIndicator(
      onRefresh: () => provider.refreshData(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              _kpi('Total Fleet', '${provider.buses.length}', MoveSyncTheme.navy),
              const SizedBox(width: 8),
              _kpi('In Service', '$activeBuses', MoveSyncTheme.teal),
              const SizedBox(width: 8),
              _kpi('Critical', '$criticalBuses', MoveSyncTheme.red),
            ],
          ),
          const SizedBox(height: 12),
          Card(
            clipBehavior: Clip.antiAlias,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.fromLTRB(12, 10, 12, 6),
                  child: Text('Fleet GPS Locations (Simulated Waypoints)', style: TextStyle(fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                ),
                SizedBox(
                  height: 185,
                  child: FlutterMap(
                    options: const MapOptions(initialCenter: LatLng(12.9716, 77.5946), initialZoom: 11.5),
                    children: [
                      TileLayer(
                        urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                        userAgentPackageName: 'com.example.passenger_mobile_app',
                      ),
                      MarkerLayer(markers: markers),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          if (cv != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Expanded(
                          child: Text('Video / Session Counting (YOLOv8 + ByteTrack)',
                              style: TextStyle(fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                        ),
                        TextButton(
                          onPressed: () => _showCountingDialog(provider),
                          child: const Text('Log Session'),
                        ),
                      ],
                    ),
                    const Text('Session-based video counting (not fleet-wide live camera streaming)',
                        style: TextStyle(fontSize: 11, color: Colors.black54)),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                      children: [
                        _pill('Boarding', '${cv.totalBoarding}', MoveSyncTheme.green),
                        _pill('Alighting', '${cv.totalAlighting}', MoveSyncTheme.amber),
                        _pill('Net Delta', '${cv.netOccupancyDelta}', MoveSyncTheme.navy),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height: 12),
          const Text('Bus-Wise Occupancy', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
          const SizedBox(height: 8),
          ...provider.buses.map((bus) {
            final c = MoveSyncTheme.statusColor(bus.occupancyStatus);
            return Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: c.withValues(alpha: 0.14),
                  child: Icon(Icons.directions_bus, color: c),
                ),
                title: Text(bus.busId, style: const TextStyle(fontWeight: FontWeight.bold)),
                subtitle: Text('Route: ${bus.currentRouteId ?? "Depot"} • ${bus.status}'),
                trailing: Text('${bus.currentOccupancy}/${bus.capacity} (${bus.occupancyPct}%)',
                    style: TextStyle(fontWeight: FontWeight.bold, color: c)),
                onTap: () async {
                  await provider.selectBus(bus);
                  if (mounted) {
                    Navigator.push(context, MaterialPageRoute(builder: (_) => TrackingScreen(bus: bus)));
                  }
                },
              ),
            );
          }),
        ],
      ),
    );
  }

  // ── 2. ALERTS TAB (ACTIVE -> ACKNOWLEDGED -> BACKEND-VERIFIED RESOLVED) ───
  Widget _buildAlertsTab(TransitProvider provider) {
    final alerts = provider.alertHistory.isNotEmpty ? provider.alertHistory : provider.alerts;
    return RefreshIndicator(
      onRefresh: () => provider.refreshData(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Overcrowding Alerts', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
          const SizedBox(height: 4),
          const Text('Acknowledging records operator review. Resolving requires occupancy to drop below 65%.',
              style: TextStyle(fontSize: 12, color: Colors.black54)),
          const SizedBox(height: 10),
          if (alerts.isEmpty)
            const Card(child: Padding(padding: EdgeInsets.all(16), child: Text('No alerts recorded.')))
          else
            ...alerts.map((alert) {
              final isCrit = alert.alertLevel == 'CRITICAL';
              final isResolved = alert.alertStatus == 'RESOLVED';
              final isAck = alert.alertStatus == 'ACKNOWLEDGED';
              final statusColor = isResolved ? MoveSyncTheme.green : (isAck ? MoveSyncTheme.amber : MoveSyncTheme.red);

              return Card(
                margin: const EdgeInsets.only(bottom: 10),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('${alert.busId} • Route ${alert.routeId}',
                              style: const TextStyle(fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
                          Chip(
                            label: Text(alert.alertStatus, style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.bold)),
                            backgroundColor: statusColor.withValues(alpha: 0.12),
                            visualDensity: VisualDensity.compact,
                          ),
                        ],
                      ),
                      Text('Alert ID: ${alert.alertId}', style: const TextStyle(fontSize: 11, color: Colors.black54)),
                      const SizedBox(height: 4),
                      Text('${isCrit ? "Critical" : "Warning"}: ${alert.currentOccupancy}/${alert.capacity} (${alert.occupancyPct}%)'),
                      if (!isResolved) ...[
                        const SizedBox(height: 8),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            if (!isAck)
                              OutlinedButton(
                                onPressed: () async {
                                  final res = await provider.acknowledgeAlert(alert.alertId);
                                  if (mounted) {
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(content: Text(res['message']?.toString() ?? 'Acknowledged')),
                                    );
                                  }
                                },
                                child: const Text('Acknowledge'),
                              ),
                            const SizedBox(width: 8),
                            ElevatedButton(
                              style: ElevatedButton.styleFrom(backgroundColor: MoveSyncTheme.teal),
                              onPressed: () async {
                                final res = await provider.resolveAlert(alert.alertId);
                                if (mounted) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(content: Text(res['message']?.toString() ?? 'Resolution checked')),
                                  );
                                }
                              },
                              child: const Text('Verify & Resolve'),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              );
            }),
        ],
      ),
    );
  }

  // ── 3. DISPATCH TAB ────────────────────────────────────────────────────────
  Widget _buildDispatchTab(TransitProvider provider) {
    return RefreshIndicator(
      onRefresh: () => provider.refreshData(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Relief Bus Recommendations (${provider.pendingDispatches.length})',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
          const SizedBox(height: 8),
          if (provider.pendingDispatches.isEmpty)
            const Card(child: Padding(padding: EdgeInsets.all(16), child: Text('No pending dispatch recommendations.')))
          else
            ...provider.pendingDispatches.map((d) => Card(
                  margin: const EdgeInsets.only(bottom: 10),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('Route ${d.routeId} • ${d.priority}', style: const TextStyle(fontWeight: FontWeight.bold)),
                            Chip(label: Text(d.authorityDecision), visualDensity: VisualDensity.compact),
                          ],
                        ),
                        Text(d.recommendedAction),
                        Text('Target Bus: ${d.sourceBusId} → Relief: ${d.recommendedReliefBusId}',
                            style: const TextStyle(fontSize: 12, color: Colors.black54)),
                        const SizedBox(height: 8),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            OutlinedButton(
                              onPressed: () => provider.decideDispatch(d.recommendationId, 'REJECTED'),
                              child: const Text('Reject'),
                            ),
                            const SizedBox(width: 8),
                            ElevatedButton(
                              style: ElevatedButton.styleFrom(backgroundColor: MoveSyncTheme.green),
                              onPressed: () => provider.decideDispatch(d.recommendationId, 'APPROVED'),
                              child: const Text('Approve Dispatch'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                )),
          const SizedBox(height: 16),
          const Text('Route Demand & Scheduling', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
          const SizedBox(height: 8),
          ...provider.routeDemand.map((r) {
            final sched = provider.schedulesByRoute[r.routeId] as Map<String, dynamic>?;
            final peakHw = sched?['peak_headway_mins'] ?? '-';
            final offHw = sched?['off_peak_headway_mins'] ?? '-';
            return Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                title: Text('Route ${r.routeId} • ${r.demandTier}', style: const TextStyle(fontWeight: FontWeight.bold)),
                subtitle: Text('Avg Load: ${r.averageOccupancyPct}% • Headway: Peak ${peakHw}m / Off-Peak ${offHw}m'),
              ),
            );
          }),
        ],
      ),
    );
  }

  // ── 4. FUEL MONITORING TAB (NO CO2 MONITORING) ─────────────────────────────
  Widget _buildFuelTab(TransitProvider provider) {
    final fuel = provider.fuelSummary;
    if (fuel == null) {
      return const Center(child: Text('Estimated fuel telemetry unavailable. Pull to refresh.'));
    }

    return RefreshIndicator(
      onRefresh: () => provider.refreshData(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.amber.shade50,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: MoveSyncTheme.amber),
            ),
            child: const Text(
              'Estimated Fuel Consumption (Simulated): Values are derived from passenger load (0.200 + 0.004 × occupancy) and are not physical sensor readings.',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _kpi('Est. Total Fuel', '${fuel.totalFuelLitres} L', MoveSyncTheme.navy),
              const SizedBox(width: 8),
              _kpi('Est. Mean / Stop', '${fuel.meanFuelPerStop} L', MoveSyncTheme.teal),
            ],
          ),
          const SizedBox(height: 16),
          const Text('Route-Wise Estimated Fuel Consumption', style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
          const SizedBox(height: 8),
          ...fuel.routeWise.map((r) => Card(
                margin: const EdgeInsets.only(bottom: 6),
                child: ListTile(
                  title: Text('Route ${r['route_id']}', style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text('Stop Events: ${r['stop_events']} • Avg: ${r['avg_fuel_per_stop']} L/stop (Estimated)'),
                  trailing: Text('${r['total_fuel_litres']} L', style: const TextStyle(fontWeight: FontWeight.bold)),
                ),
              )),
          const SizedBox(height: 16),
          const Text('Bus-Wise Estimated Fuel Consumption', style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy)),
          const SizedBox(height: 8),
          ...fuel.busWise.map((b) => Card(
                margin: const EdgeInsets.only(bottom: 6),
                child: ListTile(
                  title: Text('${b['bus_id']}', style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text('Stop Events: ${b['stop_events']} • Avg: ${b['avg_fuel_per_stop']} L/stop (Estimated)'),
                  trailing: Text('${b['total_fuel_litres']} L', style: const TextStyle(fontWeight: FontWeight.bold)),
                ),
              )),
        ],
      ),
    );
  }

  Widget _kpi(String label, String value, Color color) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
          child: Column(
            children: [
              Text(label, style: const TextStyle(fontSize: 11, color: Colors.black54), textAlign: TextAlign.center),
              const SizedBox(height: 4),
              Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: color)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _pill(String label, String value, Color color) {
    return Column(
      children: [
        Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: color)),
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.black54)),
      ],
    );
  }
}
