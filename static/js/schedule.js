document.querySelectorAll('[data-schedule]').forEach((section) => {
    const mode = section.querySelector('[name="time_mode"]');
    const clock = section.querySelector('[data-schedule-clock]');
    const period = section.querySelector('[data-schedule-period]');
    function update() {
        const needsClock = mode.value === 'exact' || mode.value === 'around';
        clock.hidden = !needsClock;
        period.hidden = mode.value !== 'period';
        clock.querySelectorAll('select').forEach((field) => {
            field.disabled = !needsClock;
            field.required = needsClock;
        });
        period.querySelectorAll('select').forEach((field) => {
            field.disabled = mode.value !== 'period';
            field.required = mode.value === 'period';
        });
        section.querySelector('[data-schedule-around]').hidden = mode.value !== 'around';
        section.querySelector('[data-schedule-consult]').hidden = mode.value !== 'consult';
    }
    mode.addEventListener('change', update);
    update();
});
