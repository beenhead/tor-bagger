class Tor {
  final int id;
  final String name;
  final double lat;
  final double lon;
  final int? elevationM;
  final double avgRating;
  final int reviewCount;

  Tor({
    required this.id,
    required this.name,
    required this.lat,
    required this.lon,
    this.elevationM,
    required this.avgRating,
    required this.reviewCount,
  });

  factory Tor.fromJson(Map<String, dynamic> json) {
    return Tor(
      id: json['id'] as int,
      name: json['name'] as String,
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      elevationM: json['elevation_m'] as int?,
      avgRating: ((json['avg_rating'] ?? 0) as num).toDouble(),
      reviewCount: (json['review_count'] ?? 0) as int,
    );
  }
}

class BaggedLog {
  final int torId;
  final String torName;
  final DateTime? baggedAt;

  BaggedLog({required this.torId, required this.torName, this.baggedAt});

  factory BaggedLog.fromJson(Map<String, dynamic> json) {
    final raw = json['bagged_at'] as String?;
    return BaggedLog(
      torId: json['tor_id'] as int,
      torName: json['tor_name'] as String,
      baggedAt: raw == null ? null : DateTime.tryParse(raw),
    );
  }
}
