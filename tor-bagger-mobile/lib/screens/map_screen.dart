import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../api/api_client.dart';
import '../auth/auth_store.dart';
import '../models/tor.dart';

class MapScreen extends StatefulWidget {
  final ApiClient api;
  final AuthStore auth;
  final VoidCallback onLoggedOut;

  const MapScreen({super.key, required this.api, required this.auth, required this.onLoggedOut});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  static const LatLng _dartmoorCentre = LatLng(50.5719, -3.9811);

  List<Tor> _tors = [];
  Set<int> _baggedIds = {};
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final tors = await widget.api.getTors();
      Set<int> bagged = {};
      try {
        bagged = await widget.api.getBaggedTorIds();
      } on ApiException {
        // Not fatal — viewing without an auth header still shows tors.
      }
      if (!mounted) return;
      setState(() {
        _tors = tors;
        _baggedIds = bagged;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _logout() async {
    await widget.auth.clear();
    widget.onLoggedOut();
  }

  Future<Position?> _currentPosition() async {
    final service = await Geolocator.isLocationServiceEnabled();
    if (!service) {
      _snack('Location services are disabled.');
      return null;
    }
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
      _snack('Location permission denied.');
      return null;
    }
    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.best),
    );
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _bag(Tor tor) async {
    Navigator.of(context).pop(); // close the sheet
    _snack('Getting your location…');
    final pos = await _currentPosition();
    if (pos == null) return;
    try {
      final msg = await widget.api.bagTor(tor.id, pos.latitude, pos.longitude);
      _snack(msg);
      await _refresh();
    } on ApiException catch (e) {
      _snack(e.message);
    }
  }

  void _openTorSheet(Tor tor) {
    final isBagged = _baggedIds.contains(tor.id);
    showModalBottomSheet(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(tor.name, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4),
            Text(
              '${tor.elevationM ?? 0} m'
              '${tor.reviewCount > 0 ? "  •  ${tor.avgRating.toStringAsFixed(1)}★ (${tor.reviewCount})" : ""}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: isBagged ? null : () => _bag(tor),
                icon: Icon(isBagged ? Icons.check_circle : Icons.flag),
                label: Text(isBagged ? 'Already Bagged' : 'Bag This Tor'),
              ),
            ),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('⛰️ Tor Bagger'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _refresh),
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout),
        ],
      ),
      body: Stack(
        children: [
          FlutterMap(
            options: const MapOptions(
              initialCenter: _dartmoorCentre,
              initialZoom: 11,
              minZoom: 8,
              maxZoom: 18,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.torbagger.tor_bagger_mobile',
              ),
              MarkerLayer(
                markers: _tors.map((tor) {
                  final bagged = _baggedIds.contains(tor.id);
                  return Marker(
                    point: LatLng(tor.lat, tor.lon),
                    width: 32,
                    height: 32,
                    child: GestureDetector(
                      onTap: () => _openTorSheet(tor),
                      child: Icon(
                        Icons.location_on,
                        size: 32,
                        color: bagged ? Colors.green.shade700 : Colors.blueGrey,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
          if (_loading)
            const Positioned(
              top: 12,
              right: 12,
              child: Card(
                child: Padding(
                  padding: EdgeInsets.all(8),
                  child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
                ),
              ),
            ),
          if (_error != null)
            Positioned(
              left: 12,
              right: 12,
              bottom: 12,
              child: Card(
                color: Colors.red.shade100,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(_error!),
                ),
              ),
            ),
          Positioned(
            left: 12,
            bottom: 12,
            child: Card(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                child: Text('${_baggedIds.length} / ${_tors.length} bagged'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
