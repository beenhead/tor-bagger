import 'package:flutter_test/flutter_test.dart';

import 'package:tor_bagger_mobile/main.dart';

void main() {
  testWidgets('App boots without throwing', (WidgetTester tester) async {
    await tester.pumpWidget(const TorBaggerApp());
    await tester.pump();
  });
}
