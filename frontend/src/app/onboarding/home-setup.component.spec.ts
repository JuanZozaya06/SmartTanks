import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ApiService } from '../core/api.service';
import { HomeSetupComponent } from './home-setup.component';

describe('HomeSetupComponent', () => {
  let createHome: jasmine.Spy;

  beforeEach(async () => {
    createHome = jasmine.createSpy('createHome').and.returnValue(of({}));
    await TestBed.configureTestingModule({
      imports: [HomeSetupComponent],
      providers: [{ provide: ApiService, useValue: { createHome } }],
    }).compileComponents();
  });

  it('creates a home without precreating tanks', async () => {
    const fixture = TestBed.createComponent(HomeSetupComponent);
    const component = fixture.componentInstance;
    component.form.setValue({ homeName: 'Mi casa', timezone: 'America/Caracas' });

    await component.submit();

    expect(createHome).toHaveBeenCalledOnceWith({
      name: 'Mi casa',
      timezone: 'America/Caracas',
      displayName: null,
    });
  });
});
