import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthStore {
  static const _tokenKey = 'tor_token';
  static const _isAdminKey = 'is_admin';

  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  Future<String?> getToken() => _storage.read(key: _tokenKey);

  Future<bool> get isLoggedIn async => (await getToken()) != null;

  Future<void> save({required String token, required bool isAdmin}) async {
    await _storage.write(key: _tokenKey, value: token);
    await _storage.write(key: _isAdminKey, value: isAdmin.toString());
  }

  Future<void> clear() async {
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _isAdminKey);
  }
}
