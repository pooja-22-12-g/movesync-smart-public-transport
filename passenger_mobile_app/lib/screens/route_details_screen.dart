import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/transit_models.dart';
import '../providers/transit_provider.dart';
import 'tracking_screen.dart';

class RouteDetailsScreen extends StatelessWidget {
  final TransitRoute route;

  const RouteDetailsScreen({Key? key, required this.route}) : super(key: key);

  Color _getStatusColor(String status) {
    switch (status) {
      case 'CRITICAL':
        return Colors.red;
      case 'WARNING':
        return Colors.orange;
      case 'NORMAL':
      default:
        return Colors.green;
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);
    final routeBuses = provider.buses.where((b) => b.currentRouteId == route.routeId).toList();

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text('Route ${route.routeId}', style: const TextStyle(fontWeight: FontWeight.bold)),
          backgroundColor: const Color(0xFF1A237E),
          foregroundColor: Colors.white,
          bottom: const TabBar(
            indicatorColor: Colors.white,
            labelColor: Colors.white,
            tabs: [
              Tab(icon: Icon(Icons.pin_drop), text: 'Stops & Timetable'),
              Tab(icon: Icon(Icons.directions_bus), text: 'Active Buses'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            // Tab 1: Stops Sequence
            ListView.builder(
              padding: const EdgeInsets.all(16.0),
              itemCount: route.stops.length,
              itemBuilder: (ctx, i) {
                final stop = route.stops[i];
                final isFirst = i == 0;
                final isLast = i == route.stops.length - 1;

                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Column(
                      children: [
                        CircleAvatar(
                          radius: 12,
                          backgroundColor: isFirst
                              ? Colors.green
                              : (isLast ? Colors.red : const Color(0xFF1A237E)),
                          child: Text('${stop.stopOrder}', style: const TextStyle(color: Colors.white, fontSize: 10)),
                        ),
                        if (!isLast)
                          Container(
                            width: 2,
                            height: 36,
                            color: Colors.grey.shade300,
                          ),
                      ],
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.only(top: 2.0),
                        child: Text(
                          stop.stopName,
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: isFirst || isLast ? FontWeight.bold : FontWeight.w500,
                          ),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),

            // Tab 2: Operating Buses on this route
            routeBuses.isEmpty
                ? const Center(child: Text('No active buses currently operating on this corridor.', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    padding: const EdgeInsets.all(16.0),
                    itemCount: routeBuses.length,
                    itemBuilder: (ctx, i) {
                      final bus = routeBuses[i];
                      final statusColor = _getStatusColor(bus.occupancyStatus);

                      return Card(
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        margin: const EdgeInsets.only(bottom: 12),
                        child: ListTile(
                          leading: CircleAvatar(
                            backgroundColor: statusColor.withOpacity(0.15),
                            child: Icon(Icons.directions_bus, color: statusColor),
                          ),
                          title: Text(bus.busId, style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Text('Last Stop: ${bus.lastStopName ?? "Terminal"}'),
                          trailing: Text(
                            '${bus.currentOccupancy}/${bus.capacity}\n${bus.availableCapacity} free',
                            textAlign: TextAlign.right,
                            style: TextStyle(fontWeight: FontWeight.bold, color: statusColor),
                          ),
                          onTap: () async {
                            await provider.selectBus(bus);
                            if (context.mounted) {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => TrackingScreen(bus: bus)),
                              );
                            }
                          },
                        ),
                      );
                    },
                  ),
          ],
        ),
      ),
    );
  }
}

