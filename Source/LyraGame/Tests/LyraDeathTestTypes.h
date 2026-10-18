// Test fixtures for executing the real Lyra death component in Unreal Engine.

#pragma once

#include "CoreMinimal.h"
#include "Character/LyraHealthComponent.h"
#include "GameFramework/Actor.h"
#include "GameplayTagContainer.h"

#include "LyraDeathTestTypes.generated.h"

class ULyraAbilitySystemComponent;
class ULyraHealthSet;

// Exposes the protected replication callback without replacing its implementation.
UCLASS(Transient, NotBlueprintable)
class ULyraDeathTestHealthComponent : public ULyraHealthComponent
{

	GENERATED_BODY()

public:
	void ApplyReplicatedStateForTest(ELyraDeathState PreviousState, ELyraDeathState IncomingState);
};

UCLASS(Transient, NotBlueprintable)
class ALyraDeathTestActor : public AActor
{

	GENERATED_BODY()

public:
	ALyraDeathTestActor(const FObjectInitializer& ObjectInitializer);

	void InitializeTest(bool bWithAbilitySystem);
	virtual void ForceNetUpdate() override;

	UPROPERTY()
	TObjectPtr<ULyraDeathTestHealthComponent> HealthComponent;

	UPROPERTY()
	TObjectPtr<ULyraAbilitySystemComponent> AbilitySystem;

	UPROPERTY()
	TObjectPtr<ULyraHealthSet> HealthSet;

	TArray<FString> Trace;
	int32 DeathStartedCount = 0;
	int32 DeathFinishedCount = 0;
	int32 ForceNetUpdateCount = 0;
	int32 WrongOwnerCount = 0;

private:
	UFUNCTION()
	void HandleDeathStarted(AActor* OwningActor);

	UFUNCTION()
	void HandleDeathFinished(AActor* OwningActor);

	void HandleTagChanged(FGameplayTag Tag, int32 NewCount);
	void RecordDeathEvent(const TCHAR* EventName, AActor* OwningActor);
};
