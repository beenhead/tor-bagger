import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'auth/auth_store.dart';
import 'auth/login_screen.dart';
import 'screens/map_screen.dart';

void main() => runApp(const TorBaggerApp());

class TorBaggerApp extends StatefulWidget {
  const TorBaggerApp({super.key});

  @override
  State<TorBaggerApp> createState() => _TorBaggerAppState();
}

class _TorBaggerAppState extends State<TorBaggerApp> {
  final AuthStore _auth = AuthStore();
  late final ApiClient _api = ApiClient(_auth);

  bool? _loggedIn;

  @override
  void initState() {
    super.initState();
    _auth.isLoggedIn.then((v) => setState(() => _loggedIn = v));
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Tor Bagger',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF27AE60)),
        useMaterial3: true,
      ),
      home: switch (_loggedIn) {
        null => const Scaffold(body: Center(child: CircularProgressIndicator())),
        true => MapScreen(
            api: _api,
            auth: _auth,
            onLoggedOut: () => setState(() => _loggedIn = false),
          ),
        false => LoginScreen(
            api: _api,
            auth: _auth,
            onLoggedIn: () => setState(() => _loggedIn = true),
          ),
      },
    );
  }
}
