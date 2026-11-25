import 'dart:convert';
import 'dart:async';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:flutter/foundation.dart';

class WebSocketService {
  // Configured via --dart-define=WS_BASE_URL=wss://... for cloud deployment;
  // defaults to local development URL when --dart-define is omitted.
  static const String defaultWsUrl = String.fromEnvironment('WS_BASE_URL', defaultValue: 'ws://192.168.1.7:8000');

  WebSocketChannel? _channel;
  final _eventController = StreamController<Map<String, dynamic>>.broadcast();
  bool _isConnected = false;

  Stream<Map<String, dynamic>> get stream => _eventController.stream;
  bool get isConnected => _isConnected;

  void connect([String wsUrl = defaultWsUrl, String? token]) {
    disconnect();
    final uri = token != null ? Uri.parse('$wsUrl/ws/live?token=$token') : Uri.parse('$wsUrl/ws/live');
    try {
      _channel = WebSocketChannel.connect(uri);
      _isConnected = true;
      _channel!.stream.listen(
        (data) {
          try {
            final parsed = jsonDecode(data);
            _eventController.add(parsed);
          } catch (e) {
            debugPrint('Error parsing WS message: $e');
          }
        },
        onError: (err) {
          debugPrint('WebSocket error: $err');
          _isConnected = false;
        },
        onDone: () {
          debugPrint('WebSocket disconnected.');
          _isConnected = false;
        },
      );
    } catch (e) {
      debugPrint('Failed to connect WebSocket: $e');
      _isConnected = false;
    }
  }

  void subscribeTopic(String topic) {
    if (_channel != null && _isConnected) {
      _channel!.sink.add(jsonEncode({
        'action': 'subscribe',
        'topic': topic,
      }));
    }
  }

  void disconnect() {
    if (_channel != null) {
      _channel!.sink.close();
      _channel = null;
      _isConnected = false;
    }
  }

  void dispose() {
    disconnect();
    _eventController.close();
  }
}

