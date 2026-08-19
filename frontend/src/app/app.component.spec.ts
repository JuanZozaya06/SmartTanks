import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { AppComponent } from './app.component';
import { ApiService } from './core/api.service';
import { AuthService } from './core/auth.service';

class AuthServiceStub {
  readonly user = signal(null);

  async logout(): Promise<void> {}
}

class ApiServiceStub {
  context() {
    return of({ user: null, home: null, tanks: [] });
  }
}

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        { provide: AuthService, useClass: AuthServiceStub },
        { provide: ApiService, useClass: ApiServiceStub },
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should require authentication instead of rendering demo data', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('El agua de tu hogar');
    expect(compiled.textContent).not.toContain('276 L');
  });
});
