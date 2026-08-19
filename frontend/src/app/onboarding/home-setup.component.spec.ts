import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ApiService } from '../core/api.service';
import { HomeSetupComponent } from './home-setup.component';

describe('HomeSetupComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HomeSetupComponent],
      providers: [{ provide: ApiService, useValue: { createHome: () => of({}) } }],
    }).compileComponents();
  });

  it('calculates cylindrical capacity from real dimensions', () => {
    const fixture = TestBed.createComponent(HomeSetupComponent);
    const component = fixture.componentInstance;
    component.form.controls.tank1Height.setValue(200);
    component.form.controls.tank1Diameter.setValue(51);

    component.calculateCapacity(1);

    expect(component.form.controls.tank1Capacity.value).toBeCloseTo(408.6, 1);
  });
});
