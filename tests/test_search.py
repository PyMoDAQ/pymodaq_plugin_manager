from pymodaq_plugin_manager.search import plugin_matches, filter_plugins, instrument_names

THORLABS = {'plugin-name': 'pymodaq_plugins_thorlabs', 'display-name': 'Thorlabs',
            'description': 'Control of Thorlabs instruments, tested with the TDC001 on Windows',
            'instruments': {'Actuators': ['Kinesis_KPZ101: Piezo Electric Stage Kinesis series (KPZ101)',
                                          'DCServoKCube: DC Servo motors controlled using a KCube'],
                            'Viewer2D': ['UC480: Interface for simple camera of the thorlabs uc480 series']}}
ANDOR = {'plugin-name': 'pymodaq_plugins_andor', 'display-name': 'Andor',
         'description': '', 'instruments': {'Viewer2D': ['AndorCCD: Andor CCD camera using the SDK2']}}
OLD = {'plugin-name': 'pymodaq_plugins_old', 'display-name': 'Old', 'description': 'nothing', 'instruments': ''}


def test_empty_text_matches_everything():
    assert all(plugin_matches(p, '') for p in (THORLABS, ANDOR, OLD))
    assert all(plugin_matches(p, '   ') for p in (THORLABS, ANDOR, OLD))


def test_search_by_instrument():
    assert filter_plugins([THORLABS, ANDOR, OLD], 'kpz101') == [THORLABS]
    assert filter_plugins([THORLABS, ANDOR, OLD], 'andorccd') == [ANDOR]
    assert filter_plugins([THORLABS, ANDOR, OLD], 'CCD camera') == [ANDOR]  # every word, in any order


def test_search_ignores_separators_and_case():
    assert plugin_matches(THORLABS, 'kinesis kpz 101')
    assert plugin_matches(THORLABS, 'Kinesis-KPZ_101')
    assert plugin_matches(THORLABS, 'servo k cube')


def test_search_by_name_only():
    assert filter_plugins([THORLABS, ANDOR], 'andor', in_instruments=False) == [ANDOR]
    assert filter_plugins([THORLABS, ANDOR], 'kpz101', in_instruments=False) == []


def test_description_is_searched_only_if_asked():
    assert not plugin_matches(THORLABS, 'tdc001')
    assert plugin_matches(THORLABS, 'tdc001', in_description=True)


def test_plugin_without_instruments_does_not_fail():
    assert instrument_names(OLD) == []
    assert not plugin_matches(OLD, 'kpz101')
    assert plugin_matches(OLD, 'old')


def test_instrument_names():
    assert instrument_names(THORLABS) == ['Kinesis_KPZ101', 'DCServoKCube', 'UC480']
