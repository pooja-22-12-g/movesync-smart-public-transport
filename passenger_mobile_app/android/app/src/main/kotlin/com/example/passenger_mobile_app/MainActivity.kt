package com.example.passenger_mobile_app

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val channelName = "com.movesync/location"
    private val permissionRequestCode = 1001
    private var pendingResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                if (call.method == "getCurrentLocation") {
                    handleGetLocation(result)
                } else {
                    result.notImplemented()
                }
            }
    }

    private fun handleGetLocation(result: MethodChannel.Result) {
        val fineGranted = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarseGranted = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!fineGranted && !coarseGranted) {
            pendingResult = result
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION),
                permissionRequestCode
            )
            return
        }
        returnLastKnownLocation(result)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == permissionRequestCode && pendingResult != null) {
            val res = pendingResult!!
            pendingResult = null
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                returnLastKnownLocation(res)
            } else {
                res.success(mapOf("error" to "Location permission denied. Use manual stop search."))
            }
        }
    }

    private fun returnLastKnownLocation(result: MethodChannel.Result) {
        try {
            val lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
            val gpsLoc: Location? = lm.getLastKnownLocation(LocationManager.GPS_PROVIDER)
            val netLoc: Location? = lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
            val best: Location? = gpsLoc ?: netLoc
            if (best != null) {
                result.success(mapOf("lat" to best.latitude, "lon" to best.longitude))
            } else {
                result.success(mapOf("error" to "GPS location unavailable. Use manual stop search."))
            }
        } catch (e: SecurityException) {
            result.success(mapOf("error" to "Location permission denied. Use manual stop search."))
        }
    }
}
