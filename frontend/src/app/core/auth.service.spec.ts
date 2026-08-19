import { authErrorMessage } from './auth.service';

describe('authErrorMessage', () => {
  it('explains when the email and password provider is disabled', () => {
    expect(authErrorMessage({ code: 'auth/operation-not-allowed' })).toContain(
      'correo y contraseña',
    );
  });
});
