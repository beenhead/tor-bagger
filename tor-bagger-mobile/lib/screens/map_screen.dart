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
  Map<int, BaggedLog> _logs = {};
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh().then((_) => _maybeShowIntro());
  }

  Future<void> _maybeShowIntro() async {
    if (await widget.auth.hasSeenIntro()) return;
    if (!mounted) return;
    await _showIntro();
    await widget.auth.markIntroSeen();
  }

  Future<void> _showIntro() {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Welcome to Tor Bagger ⛰️', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 12),
            const _HelpRow(
              icon: Icons.location_on,
              text: 'Grey pins are un-bagged Tors. Solid green pins are verified bags; '
                  'outlined green pins are self-reported visits.',
            ),
            const _HelpRow(
              icon: Icons.touch_app,
              text: 'Tap a pin to see the Tor\'s name and elevation.',
            ),
            const _HelpRow(
              icon: Icons.flag,
              text: '"Bag This Tor" uses your GPS to confirm you\'re within 150m of the summit.',
            ),
            const _HelpRow(
              icon: Icons.edit_note,
              text: '"I visited" logs a past visit without proof. It counts towards your total, '
                  'but only verified bags rank on the leaderboard. Upload a GPX track or bag it '
                  'on the summit to verify it.',
            ),
            const _HelpRow(
              icon: Icons.refresh,
              text: 'Tap refresh in the top bar to re-sync your bagged list from the server.',
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Got it'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final tors = await widget.api.getTors();
      Map<int, BaggedLog> logs = {};
      try {
        logs = await widget.api.getBaggedLogs();
      } on ApiException {
        // Not fatal — viewing without an auth header still shows tors.
      }
      if (!mounted) return;
      setState(() {
        _tors = tors;
        _logs = logs;
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

  Future<void> _recordVisit(Tor tor) async {
    final now = DateTime.now();
    final day = await showDatePicker(
      context: context,
      helpText: 'When did you visit ${tor.name}?',
      initialDate: now,
      firstDate: DateTime(1950),
      lastDate: now,
    );
    if (day == null || !mounted) return;
    Navigator.of(context).pop(); // close the sheet
    try {
      _snack(await widget.api.recordVisit(tor.id, day));
      await _refresh();
    } on ApiException catch (e) {
      _snack(e.message);
    }
  }

  Future<void> _removeVisit(Tor tor) async {
    Navigator.of(context).pop(); // close the sheet
    try {
      await widget.api.removeVisit(tor.id);
      _snack('Removed your visit to ${tor.name}.');
      await _refresh();
    } on ApiException catch (e) {
      _snack(e.message);
    }
  }

  void _openTorSheet(Tor tor) {
    final log = _logs[tor.id];
    final verified = log?.verified ?? false;
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
            if (log != null) ...[
              const SizedBox(height: 12),
              _BagStatus(log: log),
            ],
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: verified ? null : () => _bag(tor),
                icon: Icon(verified ? Icons.check_circle : Icons.flag),
                label: Text(verified
                    ? 'Already Bagged'
                    : log != null
                        ? 'Verify With GPS'
                        : 'Bag This Tor'),
              ),
            ),
            if (log == null) ...[
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => _recordVisit(tor),
                  icon: const Icon(Icons.edit_note),
                  label: const Text('I Visited'),
                ),
              ),
            ] else if (!verified) ...[
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: TextButton(
                  onPressed: () => _removeVisit(tor),
                  child: const Text('Remove Visit'),
                ),
              ),
            ],
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
          IconButton(icon: const Icon(Icons.help_outline), onPressed: _showIntro, tooltip: 'How it works'),
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
                  final log = _logs[tor.id];
                  return Marker(
                    point: LatLng(tor.lat, tor.lon),
                    width: 32,
                    height: 32,
                    child: GestureDetector(
                      onTap: () => _openTorSheet(tor),
                      child: Icon(
                        log != null && !log.verified ? Icons.location_on_outlined : Icons.location_on,
                        size: 32,
                        color: log != null ? Colors.green.shade700 : const Color(0xFF1F4E79),
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
                child: Text('${_logs.length} / ${_tors.length} bagged'
                    ' (${_logs.values.where((l) => l.verified).length} verified)'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BagStatus extends StatelessWidget {
  final BaggedLog log;
  const _BagStatus({required this.log});

  @override
  Widget build(BuildContext context) {
    final date = log.baggedAt == null
        ? ''
        : ' on ${log.baggedAt!.day}/${log.baggedAt!.month}/${log.baggedAt!.year}';
    final label = switch (log.source) {
      'gps' => 'GPS verified$date',
      'manual' => 'Self-reported$date — upload a GPX track or bag it on the summit to verify',
      _ => 'GPX verified$date',
    };
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(log.verified ? Icons.verified : Icons.edit_note, size: 18, color: Colors.green.shade700),
        const SizedBox(width: 8),
        Expanded(child: Text(label, style: Theme.of(context).textTheme.bodyMedium)),
      ],
    );
  }
}

class _HelpRow extends StatelessWidget {
  final IconData icon;
  final String text;
  const _HelpRow({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: 12),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyMedium)),
        ],
      ),
    );
  }
}
