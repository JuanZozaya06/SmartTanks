import { Injectable, signal } from '@angular/core';
import {
  User,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
} from 'firebase/auth';

import { FirebaseService } from './firebase.service';

@Injectable({ providedIn: 'root' })
export class AuthService {
  readonly user = signal<User | null | undefined>(undefined);

  constructor(private readonly firebase: FirebaseService) {
    onAuthStateChanged(this.firebase.auth, (user) => this.user.set(user));
  }

  async register(displayName: string, email: string, password: string): Promise<void> {
    const credential = await createUserWithEmailAndPassword(
      this.firebase.auth,
      email.trim(),
      password,
    );
    await updateProfile(credential.user, { displayName: displayName.trim() });
    await credential.user.getIdToken(true);
    this.user.set(credential.user);
  }

  async login(email: string, password: string): Promise<void> {
    await signInWithEmailAndPassword(this.firebase.auth, email.trim(), password);
  }

  async logout(): Promise<void> {
    await signOut(this.firebase.auth);
  }
}

export function authErrorMessage(cause: unknown): string {
  const code =
    cause && typeof cause === 'object' && 'code' in cause
      ? String((cause as { code: unknown }).code)
      : '';
  const messages: Record<string, string> = {
    'auth/email-already-in-use': 'Ese correo ya está registrado.',
    'auth/invalid-credential': 'Correo o contraseña incorrectos.',
    'auth/invalid-email': 'El correo no es válido.',
    'auth/too-many-requests': 'Demasiados intentos. Espera unos minutos.',
    'auth/weak-password': 'La contraseña debe tener al menos 6 caracteres.',
    'auth/network-request-failed': 'No pudimos conectarnos. Comprueba tu conexión e intenta nuevamente.',
    'auth/operation-not-allowed': 'El acceso no está disponible en este momento.',
  };
  return messages[code] ?? 'No fue posible completar la autenticación.';
}
