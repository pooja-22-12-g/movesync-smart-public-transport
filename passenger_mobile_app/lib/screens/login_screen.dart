import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/transit_provider.dart';
import '../theme/movesync_theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _nameController = TextEditingController();
  bool _isRegistering = false;
  bool _isAuthorityMode = false;

  void _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final provider = Provider.of<TransitProvider>(context, listen: false);
    final email = _emailController.text.trim();
    final password = _passwordController.text.trim();

    if (_isRegistering && !_isAuthorityMode) {
      final success = await provider.register(email, password, _nameController.text.trim());
      if (!success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(provider.errorMessage ?? 'Registration failed')),
        );
      }
    } else {
      final success = await provider.login(
        email,
        password,
        requireAuthority: _isAuthorityMode,
      );
      if (!success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(provider.errorMessage ?? 'Login failed')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TransitProvider>(context);

    return Scaffold(
      backgroundColor: MoveSyncTheme.lightGrey,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Hero city bus photograph with fallback
              ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: SizedBox(
                  height: 175,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      Image.asset(
                        'assets/images/welcome_bus.jpg',
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => Container(
                          color: MoveSyncTheme.navy,
                          child: const Icon(Icons.directions_bus, size: 64, color: Colors.white70),
                        ),
                      ),
                      Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Colors.transparent, MoveSyncTheme.navy.withValues(alpha: 0.85)],
                          ),
                        ),
                      ),
                      const Positioned(
                        left: 18,
                        bottom: 16,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'MoveSync',
                              style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
                            ),
                            Text(
                              'Smart Mobility. Better Journeys.',
                              style: TextStyle(fontSize: 13, color: Colors.white70),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 20),

              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: ChoiceChip(
                                showCheckmark: false,
                                labelPadding: const EdgeInsets.symmetric(horizontal: 6),
                                label: const SizedBox(
                                  width: double.infinity,
                                  child: FittedBox(
                                    fit: BoxFit.scaleDown,
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        Icon(Icons.person_outline, size: 16),
                                        SizedBox(width: 5),
                                        Text('Passenger Login'),
                                      ],
                                    ),
                                  ),
                                ),
                                selected: !_isAuthorityMode,
                                selectedColor: MoveSyncTheme.teal.withValues(alpha: 0.18),
                                onSelected: (_) => setState(() {
                                  _isAuthorityMode = false;
                                }),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: ChoiceChip(
                                showCheckmark: false,
                                labelPadding: const EdgeInsets.symmetric(horizontal: 6),
                                label: const SizedBox(
                                  width: double.infinity,
                                  child: FittedBox(
                                    fit: BoxFit.scaleDown,
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        Icon(Icons.admin_panel_settings_outlined, size: 16),
                                        SizedBox(width: 5),
                                        Text('Authority Login'),
                                      ],
                                    ),
                                  ),
                                ),
                                selected: _isAuthorityMode,
                                selectedColor: MoveSyncTheme.navy.withValues(alpha: 0.18),
                                onSelected: (_) => setState(() {
                                  _isAuthorityMode = true;
                                  _isRegistering = false;
                                }),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        Text(
                          _isAuthorityMode
                              ? 'Authority Portal Sign In'
                              : (_isRegistering ? 'Create Passenger Account' : 'Passenger Sign In'),
                          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: MoveSyncTheme.navy),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _isAuthorityMode
                              ? 'Authorized transit staff only. Passenger accounts cannot access the Authority Dashboard.'
                              : (_isRegistering
                                  ? 'Public registration is for passengers only.'
                                  : 'Sign in with your MoveSync passenger account to search stops & plan journeys.'),
                          style: const TextStyle(fontSize: 12, color: Colors.black54),
                        ),
                        const SizedBox(height: 18),
                        if (_isRegistering) ...[
                          TextFormField(
                            controller: _nameController,
                            decoration: const InputDecoration(
                              labelText: 'Full Name',
                              prefixIcon: Icon(Icons.person_outline),
                              border: OutlineInputBorder(),
                            ),
                            validator: (v) => (_isRegistering && (v == null || v.trim().isEmpty))
                                ? 'Please enter your full name'
                                : null,
                          ),
                          const SizedBox(height: 14),
                        ],
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          decoration: const InputDecoration(
                            labelText: 'Email Address',
                            prefixIcon: Icon(Icons.email_outlined),
                            border: OutlineInputBorder(),
                          ),
                          validator: (v) => (v == null || !v.contains('@')) ? 'Enter a valid email' : null,
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: true,
                          decoration: const InputDecoration(
                            labelText: 'Password',
                            prefixIcon: Icon(Icons.lock_outline),
                            border: OutlineInputBorder(),
                          ),
                          validator: (v) => (v == null || v.length < 6) ? 'Minimum 6 characters' : null,
                        ),
                        const SizedBox(height: 20),
                        SizedBox(
                          height: 48,
                          child: ElevatedButton(
                            onPressed: provider.isLoading ? null : _submit,
                            child: provider.isLoading
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                                  )
                                : Text(
                                    _isAuthorityMode
                                        ? 'Sign In to Authority Portal'
                                        : (_isRegistering ? 'Register as Passenger' : 'Sign In'),
                                    style: const TextStyle(fontSize: 15),
                                  ),
                          ),
                        ),
                        if (!_isAuthorityMode) ...[
                          const SizedBox(height: 10),
                          TextButton(
                            onPressed: () => setState(() => _isRegistering = !_isRegistering),
                            child: Text(
                              _isRegistering ? 'Already have an account? Sign In' : 'New commuter? Create an account',
                              style: const TextStyle(color: MoveSyncTheme.teal, fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
