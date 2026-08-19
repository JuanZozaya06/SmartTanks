import { authErrorMessage } from './auth.service';

describe('authErrorMessage', () => {
  it('uses a user-friendly message when access is unavailable', () => {
    expect(authErrorMessage({ code: 'auth/operation-not-allowed' })).toBe(
      'El acceso no está disponible en este momento.',
    );
  });
});
