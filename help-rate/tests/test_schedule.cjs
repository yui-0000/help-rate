const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('changing time modes shows only required inputs and keeps selections', () => {
    const hour = {value: '12'};
    const minute = {value: '00'};
    const periodField = {value: '午後'};
    const mode = {value: 'exact', addEventListener(event, callback) {this.change = callback;}};
    const clock = {querySelectorAll() {return [hour, minute];}};
    const period = {querySelectorAll() {return [periodField];}};
    const around = {};
    const consult = {};
    const elements = {'[name="time_mode"]': mode, '[data-schedule-clock]': clock,
        '[data-schedule-period]': period, '[data-schedule-around]': around,
        '[data-schedule-consult]': consult};
    const section = {querySelector(selector) {return elements[selector];}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/schedule.js'), 'utf8'), {
        document: {querySelectorAll() {return [section];}},
    });
    assert.equal(clock.hidden, false);
    assert.equal(hour.required, true);
    assert.equal(periodField.disabled, true);
    mode.value = 'period'; mode.change();
    assert.equal(clock.hidden, true);
    assert.equal(hour.disabled, true);
    assert.equal(hour.required, false);
    assert.equal(period.hidden, false);
    assert.equal(periodField.required, true);
    mode.value = 'consult'; mode.change();
    assert.equal(periodField.disabled, true);
    assert.equal(consult.hidden, false);
    mode.value = 'around'; mode.change();
    assert.equal(around.hidden, false);
    assert.equal(clock.hidden, false);
    assert.equal(hour.disabled, false);
    assert.equal(hour.value, '12');
    assert.equal(minute.value, '00');
    assert.equal(periodField.value, '午後');
});
