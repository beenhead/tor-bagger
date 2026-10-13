import 'dart:convert';
import 'package:http/http.dart' as http;

import '../auth/auth_store.dart';
import '../config.dart';
import '../models/tor.dart';

class ApiException implements Exception {
  final int? statusCode;
  final String message;
  ApiException(this.message, {this.statusCode});
  @override
  String toString() => 'ApiException($statusCode): $message';
}

class LoginResult {
  final String token;
  final bool isAdmin;
  LoginResult(this.token, this.isAdmin);
}

class ApiClient {
  final AuthStore _auth;
  ApiClient(this._auth);

  Uri _url(String path) => Uri.parse('${Config.apiBaseUrl}$path');

  Future<Map<String, String>> _authHeaders({bool json = false}) async {
    final token = await _auth.getToken();
    return {
      if (token != null) 'Authorization': 'Bearer $token',
      if (json) 'Content-Type': 'application/json',
    };
  }

  Future<LoginResult> login(String username, String password) async {
    final res = await http.post(
      _url('/token'),
      body: {'username': username, 'password': password},
    );
    if (res.statusCode != 200) {
      throw ApiException(_extractDetail(res.body) ?? 'Login failed', statusCode: res.statusCode);
    }
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return LoginResult(body['access_token'] as String, (body['is_admin'] ?? false) as bool);
  }

  Future<List<Tor>> getTors() async {
    final res = await http.get(_url('/tors'));
    if (res.statusCode != 200) {
      throw ApiException('Failed to load tors', statusCode: res.statusCode);
    }
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    final list = (body['tors'] as List).cast<Map<String, dynamic>>();
    return list.map(Tor.fromJson).toList();
  }

  /// The user's bags, keyed by tor id.
  Future<Map<int, BaggedLog>> getBaggedLogs() async {
    final res = await http.get(_url('/my-bagged-tors'), headers: await _authHeaders());
    if (res.statusCode != 200) {
      throw ApiException('Failed to load bagged tors', statusCode: res.statusCode);
    }
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    final logs = (body['logs'] as List).cast<Map<String, dynamic>>().map(BaggedLog.fromJson);
    return {for (final log in logs) log.torId: log};
  }

  /// Returns the success message from the backend.
  /// Throws [ApiException] with the backend's detail on failure (e.g. "too far away").
  Future<String> bagTor(int torId, double lat, double lon) async {
    final res = await http.post(
      _url('/tors/$torId/bag'),
      headers: await _authHeaders(json: true),
      body: jsonEncode({'user_lat': lat, 'user_lon': lon}),
    );
    final body = jsonDecode(res.body);
    if (res.statusCode != 200) {
      throw ApiException(_extractDetail(res.body) ?? 'Bagging failed', statusCode: res.statusCode);
    }
    return (body as Map<String, dynamic>)['message'] as String? ?? 'Bagged!';
  }

  /// Self-reported bag ("I visited") — no location needed.
  Future<String> recordVisit(int torId, DateTime visitedOn) async {
    final day = '${visitedOn.year.toString().padLeft(4, '0')}-'
        '${visitedOn.month.toString().padLeft(2, '0')}-'
        '${visitedOn.day.toString().padLeft(2, '0')}';
    final res = await http.post(
      _url('/tors/$torId/visit'),
      headers: await _authHeaders(json: true),
      body: jsonEncode({'visited_on': day}),
    );
    if (res.statusCode != 200) {
      throw ApiException(_extractDetail(res.body) ?? 'Could not record visit', statusCode: res.statusCode);
    }
    return (jsonDecode(res.body) as Map<String, dynamic>)['message'] as String? ?? 'Visit logged.';
  }

  /// Removes a self-reported bag. The backend refuses for verified ones.
  Future<void> removeVisit(int torId) async {
    final res = await http.delete(_url('/tors/$torId/visit'), headers: await _authHeaders());
    if (res.statusCode != 200) {
      throw ApiException(_extractDetail(res.body) ?? 'Could not remove visit', statusCode: res.statusCode);
    }
  }

  String? _extractDetail(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map && decoded['detail'] is String) return decoded['detail'] as String;
    } catch (_) {}
    return null;
  }
}
