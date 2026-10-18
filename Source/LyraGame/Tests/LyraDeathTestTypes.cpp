// Test fixtures for executing the real Lyra death component in Unreal Engine.

#include "Tests/LyraDeathTestTypes.h"

#include "AbilitySystem/Attributes/LyraHealthSet.h"
#include "AbilitySystem/LyraAbilitySystemComponent.h"
#include "LyraGameplayTags.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(LyraDeathTestTypes)

void ULyraDeathTestHealthComponent::ApplyReplicatedStateForTest(
	ELyraDeathState PreviousState, ELyraDeathState IncomingState)
{
	// Exercise the real callback with the values supplied by replication. This
	// fixture does not send packets or claim to test the replication transport.
	DeathState = IncomingState;
	OnRep_DeathState(PreviousState);
}

ALyraDeathTestActor::ALyraDeathTestActor(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	HealthComponent = CreateDefaultSubobject<ULyraDeathTestHealthComponent>(TEXT("HealthComponent"));
	AbilitySystem = CreateDefaultSubobject<ULyraAbilitySystemComponent>(TEXT("AbilitySystem"));
	HealthSet = CreateDefaultSubobject<ULyraHealthSet>(TEXT("HealthSet"));
	SetReplicates(true);
}

void ALyraDeathTestActor::InitializeTest(bool bWithAbilitySystem)
{
	if (bWithAbilitySystem)
	{
		AbilitySystem->AddAttributeSetSubobject(HealthSet.Get());
		AbilitySystem->InitAbilityActorInfo(this, this);
		HealthComponent->InitializeWithAbilitySystem(AbilitySystem.Get());
	}

	AbilitySystem->RegisterGameplayTagEvent(LyraGameplayTags::Status_Death_Dying,
		EGameplayTagEventType::AnyCountChange).AddUObject(this, &ThisClass::HandleTagChanged);
	AbilitySystem->RegisterGameplayTagEvent(LyraGameplayTags::Status_Death_Dead,
		EGameplayTagEventType::AnyCountChange).AddUObject(this, &ThisClass::HandleTagChanged);
	HealthComponent->OnDeathStarted.AddDynamic(this, &ThisClass::HandleDeathStarted);
	HealthComponent->OnDeathFinished.AddDynamic(this, &ThisClass::HandleDeathFinished);

	// Actor creation/initialization is outside each measured transition sequence.
	Trace.Reset();
	DeathStartedCount = 0;
	DeathFinishedCount = 0;
	ForceNetUpdateCount = 0;
	WrongOwnerCount = 0;
}

void ALyraDeathTestActor::ForceNetUpdate()
{
	++ForceNetUpdateCount;
	Trace.Add(TEXT("ForceNetUpdate"));
	Super::ForceNetUpdate();
}

void ALyraDeathTestActor::HandleDeathStarted(AActor* OwningActor)
{
	++DeathStartedCount;
	RecordDeathEvent(TEXT("Start"), OwningActor);
}

void ALyraDeathTestActor::HandleDeathFinished(AActor* OwningActor)
{
	++DeathFinishedCount;
	RecordDeathEvent(TEXT("Finish"), OwningActor);
}

void ALyraDeathTestActor::RecordDeathEvent(const TCHAR* EventName, AActor* OwningActor)
{
	if (OwningActor != this)
	{
		++WrongOwnerCount;
	}
	Trace.Add(FString::Printf(TEXT("%s:%d:Dying=%d:Dead=%d"), EventName,
		static_cast<int32>(HealthComponent->GetDeathState()),
		AbilitySystem->GetTagCount(LyraGameplayTags::Status_Death_Dying),
		AbilitySystem->GetTagCount(LyraGameplayTags::Status_Death_Dead)));
}

void ALyraDeathTestActor::HandleTagChanged(FGameplayTag Tag, int32 NewCount)
{
	const TCHAR* Name = (Tag == LyraGameplayTags::Status_Death_Dying) ? TEXT("Dying") : TEXT("Dead");
	Trace.Add(FString::Printf(TEXT("Tag:%s=%d"), Name, NewCount));
}
