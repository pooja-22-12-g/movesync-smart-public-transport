"""
Real-Time Updates, WebSocket Manager & Notification Service
Part of Module 7: Firebase Backend Development
Smart Public Transport Occupancy and Fleet Monitoring System

Capabilities:
1. Real-Time WebSocket Connection Manager for bidirectional event streaming:
   - Topic subscriptions: 'route_{route_id}', 'authority_alerts', 'bus_locations'
   - Role-based channel gating (passengers blocked from authority streams).
2. Firebase Cloud Messaging (FCM) Integration:
   - Broadcasts to topics ('authority_alerts', 'route_{route_id}').
   - In Mock Mode: Records notification events in-memory without sending external network requests.
   - In Live Mode: Uses firebase_admin.messaging to send real push notifications.
3. Duplicate Notification Suppression:
   - Implements sliding-window deduplication cache to prevent alert spamming.
4. Broadcasts live vehicle movements, crowding alerts, and dispatch approvals.
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass, field

from config.firebase_config import get_firebase_app, FirebaseStatus

logger = logging.getLogger("NotificationService")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

@dataclass
class NotificationRecord:
    notification_id: str
    topic: str
    title: str
    body: str
    data: Dict[str, str]
    target_role: str
    sent_at: float
    is_mock: bool

class WebSocketManager:
    """
    Manages active client WebSocket connections and topic subscriptions.
    Enforces role verification so commuters cannot subscribe to authority topics.
    """
    def __init__(self):
        # socket_id -> { "ws": WebSocket, "role": str, "topics": set() }
        self._active_connections: Dict[str, Dict[str, Any]] = {}

    def register_client(self, socket_id: str, ws_handle: Any, user_role: str = "passenger"):
        self._active_connections[socket_id] = {
            "ws": ws_handle,
            "role": user_role,
            "topics": set(["public"])
        }
        logger.info(f"WebSocket client connected: {socket_id} (Role: {user_role})")

    def unregister_client(self, socket_id: str):
        if socket_id in self._active_connections:
            del self._active_connections[socket_id]
            logger.info(f"WebSocket client disconnected: {socket_id}")

    def subscribe_topic(self, socket_id: str, topic: str) -> Tuple[bool, str]:
        client = self._active_connections.get(socket_id)
        if not client:
            return False, "Client not connected."

        # Role-based topic gate
        if topic.startswith("authority_") and client["role"] not in ["authority", "administrator"]:
            return False, f"Access denied: Topic '{topic}' is restricted to authority users."

        client["topics"].add(topic)
        logger.info(f"Client {socket_id} subscribed to '{topic}'")
        return True, f"Subscribed to {topic}"

    def unsubscribe_topic(self, socket_id: str, topic: str):
        client = self._active_connections.get(socket_id)
        if client and topic in client["topics"]:
            client["topics"].remove(topic)

    async def broadcast_to_topic(self, topic: str, message: Dict[str, Any]) -> int:
        delivered = 0
        payload = json.dumps({"topic": topic, "payload": message, "timestamp": time.time()})
        for sock_id, client in list(self._active_connections.items()):
            if topic in client["topics"]:
                ws = client["ws"]
                try:
                    if hasattr(ws, "send_text"):
                        await ws.send_text(payload)
                    elif hasattr(ws, "send"):
                        await ws.send(payload)
                    delivered += 1
                except Exception as e:
                    logger.warning(f"Failed sending to {sock_id}: {e}")
                    self.unregister_client(sock_id)
        return delivered


class NotificationService:
    def __init__(self, credentials_path: Optional[str] = None):
        self.db, self.status = get_firebase_app(credentials_path)
        self.ws_manager = WebSocketManager()
        self._dedup_cache: Dict[str, float] = {}
        self._mock_notification_log: List[NotificationRecord] = []
        self._dedup_window_seconds = 180 # 3 minutes dedup suppression
        logger.info(f"NotificationService initialized in {self.status.mode} mode.")

    def _is_duplicate(self, dedup_key: str) -> bool:
        """Check if identical alert occurred within deduplication window."""
        now = time.time()
        last_sent = self._dedup_cache.get(dedup_key)
        if last_sent and (now - last_sent) < self._dedup_window_seconds:
            return True
        self._dedup_cache[dedup_key] = now
        return False

    def send_crowding_alert(self, bus_id: str, route_id: str, current_occupancy: int, capacity: int = 50) -> Optional[NotificationRecord]:
        """
        Generate and broadcast overcrowding alert.
        Routes:
        - Critical (>90% / >=45 pax): Dispatched to 'authority_alerts'
        - Warning (>70% / >=35 pax): Dispatched to 'route_{route_id}'
        """
        occ_pct = round((current_occupancy / capacity) * 100.0, 1)
        if occ_pct >= 90.0:
            level = "CRITICAL"
            topic = "authority_alerts"
            target_role = "authority"
            title = f"[CRITICAL CROWDING] Bus {bus_id}"
            body = f"Bus {bus_id} on {route_id} reached {current_occupancy}/{capacity} passengers ({occ_pct}%). Immediate dispatch attention required."
        elif occ_pct >= 70.0:
            level = "WARNING"
            topic = f"route_{route_id}"
            target_role = "passenger"
            title = f"[WARNING CROWDING] Bus {bus_id} Approaching on {route_id}"
            body = f"Bus {bus_id} on route {route_id} has heavy occupancy ({current_occupancy}/{capacity} seats filled)."
        else:
            return None # Normal occupancy does not trigger push notification

        dedup_key = f"{bus_id}_{level}_{int(time.time() // self._dedup_window_seconds)}"
        if self._is_duplicate(dedup_key):
            logger.info(f"Suppressed duplicate alert for {bus_id} (Level: {level})")
            return None

        notif_id = f"notif_{bus_id}_{int(time.time())}"
        data_payload = {
            "bus_id": str(bus_id),
            "route_id": str(route_id),
            "occupancy": str(current_occupancy),
            "occupancy_pct": str(occ_pct),
            "alert_level": level,
            "data_provenance": "RULE_ENGINE_DERIVED"
        }

        record = NotificationRecord(
            notification_id=notif_id,
            topic=topic,
            title=title,
            body=body,
            data=data_payload,
            target_role=target_role,
            sent_at=time.time(),
            is_mock=not self.status.is_live
        )

        if not self.status.is_live:
            # Mock Mode: record locally, do not make external HTTP calls
            self._mock_notification_log.append(record)
            logger.info(f"[MOCK FCM] Dispatched push to topic '{topic}': '{title}'")
        else:
            # Live Mode: dispatch through real Firebase Cloud Messaging Admin SDK
            try:
                import firebase_admin.messaging as fcm
                message = fcm.Message(
                    notification=fcm.Notification(title=title, body=body),
                    data=data_payload,
                    topic=topic
                )
                fcm.send(message)
                logger.info(f"[LIVE FCM] Sent push to topic '{topic}': '{title}'")
            except Exception as e:
                logger.error(f"Failed to send live FCM notification: {e}")

        return record

    def send_relief_dispatch_notice(self, route_id: str, relief_bus_id: str, source_bus_id: str) -> NotificationRecord:
        """Notify commuters and authority controllers when a relief bus is approved."""
        topic = f"route_{route_id}"
        notif_id = f"relief_{relief_bus_id}_{int(time.time())}"
        title = f"[RELIEF BUS DISPATCHED] Route {route_id}"
        body = f"Relief bus {relief_bus_id} is entering service on {route_id} to relieve overcrowded bus {source_bus_id}."
        data_payload = {
            "route_id": str(route_id),
            "relief_bus_id": str(relief_bus_id),
            "source_bus_id": str(source_bus_id),
            "event_type": "RELIEF_DISPATCH",
            "data_provenance": "AUTHORITY_INTERVENTION"
        }

        record = NotificationRecord(
            notification_id=notif_id,
            topic=topic,
            title=title,
            body=body,
            data=data_payload,
            target_role="passenger",
            sent_at=time.time(),
            is_mock=not self.status.is_live
        )

        if not self.status.is_live:
            self._mock_notification_log.append(record)
            logger.info(f"[MOCK FCM] Dispatched relief notice to '{topic}': '{title}'")
        else:
            try:
                import firebase_admin.messaging as fcm
                msg = fcm.Message(
                    notification=fcm.Notification(title=title, body=body),
                    data=data_payload,
                    topic=topic
                )
                fcm.send(msg)
            except Exception as e:
                logger.error(f"Failed sending relief FCM: {e}")

        return record

    def get_notification_log(self) -> List[Dict[str, Any]]:
        return [
            {
                "notification_id": r.notification_id,
                "topic": r.topic,
                "title": r.title,
                "body": r.body,
                "target_role": r.target_role,
                "sent_at": r.sent_at,
                "is_mock": r.is_mock
            }
            for r in self._mock_notification_log
        ]
