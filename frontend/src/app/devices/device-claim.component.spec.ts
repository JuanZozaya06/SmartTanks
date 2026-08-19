import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ApiService } from '../core/api.service';
import { DeviceClaimComponent } from './device-claim.component';

describe('DeviceClaimComponent', () => {
  let claimDevice: jasmine.Spy;

  beforeEach(async () => {
    claimDevice = jasmine.createSpy('claimDevice').and.returnValue(
      of({
        device: {
          id: 'smarttank-84f703123456',
          label: 'SmartTank del patio',
          status: 'active',
          firmwareVersion: null,
          lastSeenAt: null,
          claimedAt: '2026-08-19T12:00:00Z',
        },
      }),
    );
    await TestBed.configureTestingModule({
      imports: [DeviceClaimComponent],
      providers: [
        {
          provide: ApiService,
          useValue: { claimDevice },
        },
      ],
    }).compileComponents();
  });

  it('claims a preprovisioned SmartTank with its display name', async () => {
    const fixture = TestBed.createComponent(DeviceClaimComponent);
    fixture.componentRef.setInput('homeId', 'home_01');
    fixture.componentInstance.claimForm.setValue({
      deviceId: 'smarttank-84f703123456',
      setupPin: '12345678',
      label: 'SmartTank del patio',
    });

    await fixture.componentInstance.claim();

    expect(claimDevice).toHaveBeenCalledOnceWith(
      'home_01',
      'smarttank-84f703123456',
      '12345678',
      'SmartTank del patio',
    );
  });
});
