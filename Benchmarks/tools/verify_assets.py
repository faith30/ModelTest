"""UE 5.8 editor Python: read back the stripped baseline; never save packages.

Run after compiling the selected branch's project modules. This checks starter
assets, not a candidate implementation; restored behavior should fail this check.
"""
import json
from pathlib import Path
import traceback
import unreal

root = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
feature = next(p.name for p in (root / 'Benchmarks').iterdir() if (p / 'scope.json').exists())
report = {'feature': feature, 'kind': 'stripped-baseline-readback', 'blueprints': [], 'checks': [], 'errors': []}
allowed = {'K2Node_FunctionEntry', 'K2Node_FunctionResult', 'K2Node_CustomEvent', 'K2Node_Tunnel'}

def check(label, condition):
    report['checks'].append({'name': label, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(label)

def load(path):
    obj = unreal.load_asset(path)
    check('load ' + path, obj is not None)
    return obj

def default(path):
    return unreal.get_default_object(load(path).generated_class())

def blueprint(path):
    obj = load(path)
    entry = {'path': path, 'graphs': []}
    for graph in unreal.BlueprintEditorLibrary.list_graphs(obj):
        editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
        nodes = list(editor.list_all_nodes())
        classes = [n.get_class().get_name() for n in nodes]
        check('no implementation nodes ' + path + ':' + graph.get_name(), all(c in allowed for c in classes))
        check('no graph comments ' + path + ':' + graph.get_name(), len(editor.list_comment_nodes()) == 0)
        entry['graphs'].append({'name': graph.get_name(), 'signature_nodes': len(nodes)})
    entry['compile_succeeded'] = unreal.BlueprintEditorLibrary.compile_blueprint(obj)
    check('compile ' + path, entry['compile_succeeded'])
    report['blueprints'].append(entry)

try:
    if feature == 'interaction':
        scope = json.loads((root / 'Benchmarks' / feature / 'scope.json').read_text(encoding='utf-8-sig'))
        for path in scope['blueprint_shell_assets']:
            blueprint(path)
        check('no default prompt', default('/ShooterExplorer/Input/Abilities/GA_Interact').get_editor_property('DefaultInteractionWidgetClass') is None)
        check('no inventory widget class', default('/ShooterExplorer/Input/Abilities/GA_ToggleInventory').get_editor_property('WidgetToSpawn') is None)
        rock = default('/ShooterExplorer/Items/B_InteractableRock')
        option = rock.get_editor_property('Option')
        check('no collect ability', option.get_editor_property('InteractionAbilityToGrant') is None)
        check('no collect prompt', option.get_editor_property('InteractionWidgetClass') is None)
        inventory = rock.get_editor_property('StaticInventory')
        check('empty pickup templates', len(inventory.get_editor_property('Templates')) == 0)
        check('empty pickup instances', len(inventory.get_editor_property('Instances')) == 0)
        abilities = load('/ShooterExplorer/Input/Abilities/AbilitySet_InventoryTest').get_editor_property('GrantedGameplayAbilities')
        names = [x.get_editor_property('Ability').get_name() for x in abilities]
        check('feature abilities removed; other abilities retained', not {'GA_Interact_C', 'GA_ToggleInventory_C'} & set(names) and len(names) > 0)
        inputs = load('/ShooterExplorer/Input/Actions/InputData_InventoryTest')
        names = [x.get_editor_property('InputAction').get_name() for x in inputs.get_editor_property('AbilityInputActions')]
        check('feature input tags removed; other actions retained', not {'IA_Interact', 'IA_ToggleInventory'} & set(names) and len(names) > 0)
        check('native movement input retained', len(inputs.get_editor_property('NativeInputActions')) > 0)
        mapping = load('/ShooterExplorer/Input/Mappings/IMC_InventoryTest')
        names = [x.get_editor_property('Action').get_name() for x in mapping.get_editor_property('DefaultKeyMappings').get_editor_property('Mappings')]
        check('feature keys removed; other keys retained', not {'IA_Interact', 'IA_ToggleInventory'} & set(names) and len(names) > 0)
        shared = ['/ShooterExplorer/System/Experiences/B_TestInventoryExperience', '/ShooterExplorer/System/Experiences/LAS_InventoryTest', '/ShooterExplorer/Items/B_InteractableChair']
    elif feature == 'accolades':
        for path in ['/ShooterCore/Accolades/B_ElimChainProcessor', '/ShooterCore/Accolades/B_ElimStreakProcessor', '/ShooterCore/Accolades/B_AccoladeRelay', '/ShooterCore/UserInterface/Notifications/Accolades/W_AccoladeHostWidget', '/ShooterCore/UserInterface/Notifications/Accolades/W_AccoladeToast']:
            blueprint(path)
        check('empty chain map', len(default('/ShooterCore/Accolades/B_ElimChainProcessor').get_editor_property('ElimChainTags')) == 0)
        check('empty streak map', len(default('/ShooterCore/Accolades/B_ElimStreakProcessor').get_editor_property('ElimStreakTags')) == 0)
        check('empty data registry sources', len(load('/ShooterCore/Accolades/AccoladeDataRegistry').get_editor_property('DataSources')) == 0)
        check('empty accolade table', len(unreal.DataTableFunctionLibrary.get_data_table_row_names(load('/ShooterCore/Accolades/DT_BasicShooterAccolades'))) == 0)
        toast = load('/ShooterCore/UserInterface/Notifications/Accolades/W_AccoladeToast')
        api = unreal.get_default_object(unreal.load_class(None, '/Script/UMGToolSet.UMGToolSet'))
        check('empty toast widget layout', len(api.call_method('GetWidgets', args=(toast,)).get_editor_property('Widgets')) == 0)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        for prop in ('Animations', 'Bindings'):
            unreal.SystemLibrary.execute_console_command(world, 'getall WidgetBlueprint ' + prop + ' OUTER=' + toast.get_outer().get_path_name() + ' NAME=' + toast.get_name())
        report['additional_log_checks'] = 'GETALL Animations and Bindings must contain no array elements for W_AccoladeToast.'
        shared = ['/ShooterCore/Accolades/EAS_BasicShooterAcolades', '/ShooterCore/Accolades/B_EliminationFeedRelay', '/ShooterCore/Experiences/LAS_ShooterGame_StandardHUD', '/ShooterCore/Experiences/B_ShooterGame_Elimination']
    elif feature == 'context-effects':
        blueprint('/Game/Effects/Blueprints/B_FootStep')
        blueprint('/Game/Characters/Heroes/Mannequin/Animations/AnimModifiers/FootstepEffectTagModifier')
        check('empty context effects library', len(load('/Game/ContextEffects/CFX_DefaultSkin').get_editor_property('ContextEffects')) == 0)
        foot = default('/Game/Effects/Blueprints/B_FootStep')
        check('public right foot bone retained', foot.get_editor_property('FootStepRightFootBone') is not None)
        check('surface map empty', 'SurfaceTypeToContextMap=()' in (root / 'Config' / 'DefaultGame.ini').read_text(encoding='utf-8-sig'))
        shared = ['/Game/Characters/Heroes/B_Hero_Default', '/Game/ContextEffects/DT_AnimEffectTags', '/Game/ContextEffects/DT_SurfaceTypes']
    else:
        raise RuntimeError('Unknown feature: ' + feature)
    for path in shared:
        obj = load(path)
        if isinstance(obj, unreal.Blueprint):
            check('shared blueprint compiles ' + path, unreal.BlueprintEditorLibrary.compile_blueprint(obj))
except Exception:
    report['errors'].append(traceback.format_exc())
finally:
    report['passed'] = not report['errors']
    out = root / 'Saved' / 'BenchmarkPreparation' / 'readback.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('BENCHMARK_READBACK ' + str(out))
if report['errors']:
    raise RuntimeError(report['errors'][0])
