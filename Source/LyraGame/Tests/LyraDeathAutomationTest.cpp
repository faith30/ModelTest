// Executes candidate Lyra C++ in a real UE world with a real ASC and delegates.

#include "Tests/LyraDeathTestTypes.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AbilitySystem/LyraAbilitySystemComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "LyraGameplayTags.h"
#include "Misc/AutomationTest.h"

struct FLyraDeathTestCase
{
	FString Name;
	TArray<FString> Actions;
	ELyraDeathState ExpectedState;
	int32 ExpectedStarted;
	int32 ExpectedFinished;
	bool bWithAbilitySystem = true;
};

static TArray<FLyraDeathTestCase> GetLyraDeathTestCases()
{
	using EState = ELyraDeathState;
	return {
		{TEXT("DirectFinished.SkipStartedNotification"), {TEXT("Rep02")}, EState::DeathFinished, 1, 1},
		{TEXT("DirectFinished.DuplicateFinishedSnapshot"), {TEXT("Rep02"), TEXT("Rep22")}, EState::DeathFinished, 1, 1},
		{TEXT("DirectFinished.ThenDuplicateMethods"), {TEXT("Rep02"), TEXT("Start"), TEXT("Finish")}, EState::DeathFinished, 1, 1},
		{TEXT("DirectFinished.AfterPrematureFinish"), {TEXT("Finish"), TEXT("Rep02")}, EState::DeathFinished, 1, 1},

		{TEXT("StepSequence.ReplicatedStart"), {TEXT("Rep01")}, EState::DeathStarted, 1, 0},
		{TEXT("StepSequence.ReplicatedStartAndFinish"), {TEXT("Rep01"), TEXT("Rep12")}, EState::DeathFinished, 1, 1},
		{TEXT("StepSequence.LocalStartReplicatedFinish"), {TEXT("Start"), TEXT("Rep12")}, EState::DeathFinished, 1, 1},
		{TEXT("StepSequence.ReplicatedStartLocalFinish"), {TEXT("Rep01"), TEXT("Finish")}, EState::DeathFinished, 1, 1},

		{TEXT("Idempotence.FinishBeforeStart"), {TEXT("Finish")}, EState::NotDead, 0, 0},
		{TEXT("Idempotence.DuplicateStart"), {TEXT("Start"), TEXT("Start")}, EState::DeathStarted, 1, 0},
		{TEXT("Idempotence.DuplicateFinish"), {TEXT("Start"), TEXT("Finish"), TEXT("Finish")}, EState::DeathFinished, 1, 1},
		{TEXT("Idempotence.StartAfterFinished"), {TEXT("Start"), TEXT("Finish"), TEXT("Start")}, EState::DeathFinished, 1, 1},
		{TEXT("Idempotence.RepeatedSequence"), {TEXT("Start"), TEXT("Finish"), TEXT("Start"), TEXT("Finish")}, EState::DeathFinished, 1, 1},

		{TEXT("PredictionAhead.StartedReceivesNotDead"), {TEXT("Start"), TEXT("Rep10")}, EState::DeathStarted, 1, 0},
		{TEXT("PredictionAhead.FinishedReceivesStarted"), {TEXT("Start"), TEXT("Finish"), TEXT("Rep21")}, EState::DeathFinished, 1, 1},
		{TEXT("PredictionAhead.FinishedReceivesNotDead"), {TEXT("Start"), TEXT("Finish"), TEXT("Rep20")}, EState::DeathFinished, 1, 1},
		{TEXT("PredictionAhead.RepeatedOlderState"), {TEXT("Start"), TEXT("Rep10"), TEXT("Rep10")}, EState::DeathStarted, 1, 0},
		{TEXT("PredictionAhead.TwoOlderStates"), {TEXT("Start"), TEXT("Finish"), TEXT("Rep21"), TEXT("Rep20")}, EState::DeathFinished, 1, 1},

		{TEXT("ASCNull.LocalSequence"), {TEXT("Start"), TEXT("Finish")}, EState::DeathFinished, 1, 1, false},
		{TEXT("ASCNull.DirectFinished"), {TEXT("Rep02")}, EState::DeathFinished, 1, 1, false},
		{TEXT("ASCNull.FinishBeforeStart"), {TEXT("Finish")}, EState::NotDead, 0, 0, false},
		{TEXT("ASCNull.DuplicateMethods"), {TEXT("Start"), TEXT("Start"), TEXT("Finish"), TEXT("Finish")}, EState::DeathFinished, 1, 1, false},
		{TEXT("ASCNull.PredictionAhead"), {TEXT("Start"), TEXT("Finish"), TEXT("Rep20")}, EState::DeathFinished, 1, 1, false},
	};
}

struct FLyraDeathScopedWorld
{
	UWorld* World = nullptr;

	FLyraDeathScopedWorld()
	{
		if (GEngine)
		{
			World = UWorld::CreateWorld(EWorldType::Game, false);
			if (World)
			{
				FWorldContext& Context = GEngine->CreateNewWorldContext(EWorldType::Game);
				Context.SetCurrentWorld(World);
				World->InitializeActorsForPlay(FURL());
				World->BeginPlay();
			}
		}
	}

	~FLyraDeathScopedWorld()
	{
		if (World)
		{
			World->EndPlay(EEndPlayReason::Quit);
			GEngine->DestroyWorldContext(World);
			World->DestroyWorld(false);
		}
	}
};

IMPLEMENT_COMPLEX_AUTOMATION_TEST(FLyraDeathAutomationTest, "Lyra.Benchmark.Death",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

void FLyraDeathAutomationTest::GetTests(TArray<FString>& OutBeautifiedNames, TArray<FString>& OutTestCommands) const
{
	for (const FLyraDeathTestCase& TestCase : GetLyraDeathTestCases())
	{
		OutBeautifiedNames.Add(TestCase.Name);
		OutTestCommands.Add(TestCase.Name);
	}
}

bool FLyraDeathAutomationTest::RunTest(const FString& Parameters)
{
	const TArray<FLyraDeathTestCase> TestCases = GetLyraDeathTestCases();
	const FLyraDeathTestCase* TestCase = TestCases.FindByPredicate([&Parameters](const FLyraDeathTestCase& Item)
	{
		return Item.Name == Parameters;
	});
	if (!TestNotNull(TEXT("Known independently defined test case"), TestCase))
	{
		return false;
	}

	FLyraDeathScopedWorld TestWorld;
	if (!TestNotNull(TEXT("Real game world"), TestWorld.World))
	{
		return false;
	}
	ALyraDeathTestActor* Actor = TestWorld.World->SpawnActor<ALyraDeathTestActor>();
	if (!TestNotNull(TEXT("Real test actor"), Actor))
	{
		return false;
	}
	Actor->InitializeTest(TestCase->bWithAbilitySystem);

	bool bSuccess = true;
	for (const FString& Action : TestCase->Actions)
	{
		if (Action == TEXT("Start"))
		{
			Actor->HealthComponent->StartDeath();
		}
		else if (Action == TEXT("Finish"))
		{
			Actor->HealthComponent->FinishDeath();
		}
		else if (Action.StartsWith(TEXT("Rep")) && Action.Len() == 5)
		{
			Actor->HealthComponent->ApplyReplicatedStateForTest(
				static_cast<ELyraDeathState>(Action[3] - TCHAR('0')),
				static_cast<ELyraDeathState>(Action[4] - TCHAR('0')));
		}
		else
		{
			AddError(FString::Printf(TEXT("Unknown evaluator action: %s"), *Action));
			bSuccess = false;
		}
	}

	const int32 ExpectedDying = (TestCase->bWithAbilitySystem && TestCase->ExpectedStarted > 0) ? 1 : 0;
	const int32 ExpectedDead = (TestCase->bWithAbilitySystem && TestCase->ExpectedFinished > 0) ? 1 : 0;
	bSuccess &= TestEqual(TEXT("Death state"), Actor->HealthComponent->GetDeathState(), TestCase->ExpectedState);
	bSuccess &= TestEqual(TEXT("Start delegate count"), Actor->DeathStartedCount, TestCase->ExpectedStarted);
	bSuccess &= TestEqual(TEXT("Finish delegate count"), Actor->DeathFinishedCount, TestCase->ExpectedFinished);
	bSuccess &= TestEqual(TEXT("Delegate owner identity failures"), Actor->WrongOwnerCount, 0);
	bSuccess &= TestEqual(TEXT("Dying tag count"), Actor->AbilitySystem->GetTagCount(LyraGameplayTags::Status_Death_Dying), ExpectedDying);
	bSuccess &= TestEqual(TEXT("Dead tag count"), Actor->AbilitySystem->GetTagCount(LyraGameplayTags::Status_Death_Dead), ExpectedDead);
	bSuccess &= TestEqual(TEXT("ForceNetUpdate invocation count"), Actor->ForceNetUpdateCount,
		TestCase->ExpectedStarted + TestCase->ExpectedFinished);

	TArray<FString> ExpectedTrace;
	if (TestCase->ExpectedStarted > 0)
	{
		if (TestCase->bWithAbilitySystem)
		{
			ExpectedTrace.Add(TEXT("Tag:Dying=1"));
		}
		ExpectedTrace.Add(FString::Printf(TEXT("Start:1:Dying=%d:Dead=0"), ExpectedDying));
		ExpectedTrace.Add(TEXT("ForceNetUpdate"));
	}
	if (TestCase->ExpectedFinished > 0)
	{
		if (TestCase->bWithAbilitySystem)
		{
			ExpectedTrace.Add(TEXT("Tag:Dead=1"));
		}
		ExpectedTrace.Add(FString::Printf(TEXT("Finish:2:Dying=%d:Dead=%d"), ExpectedDying, ExpectedDead));
		ExpectedTrace.Add(TEXT("ForceNetUpdate"));
	}
	bSuccess &= TestEqual(TEXT("Real tag/delegate/update order and callback state"),
		FString::Join(Actor->Trace, TEXT(" | ")), FString::Join(ExpectedTrace, TEXT(" | ")));
	AddInfo(FString::Printf(TEXT("[LyraDeathBenchmark] Case=%s State=%d Started=%d Finished=%d Dying=%d Dead=%d ForceNetUpdate=%d Passed=%s"),
		*Parameters, static_cast<int32>(Actor->HealthComponent->GetDeathState()), Actor->DeathStartedCount,
		Actor->DeathFinishedCount, Actor->AbilitySystem->GetTagCount(LyraGameplayTags::Status_Death_Dying),
		Actor->AbilitySystem->GetTagCount(LyraGameplayTags::Status_Death_Dead), Actor->ForceNetUpdateCount,
		bSuccess ? TEXT("true") : TEXT("false")));
	return bSuccess;
}

#endif // WITH_DEV_AUTOMATION_TESTS
