// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Messages/GameplayMessageProcessor.h"

#include "ElimStreakProcessor.generated.h"

// Tracks a streak of eliminations (X eliminations without being eliminated)
UCLASS(Abstract)
class UElimStreakProcessor : public UGameplayMessageProcessor
{
	GENERATED_BODY()

public:
	virtual void StartListening() override;

protected:
	// The event to rebroadcast when a user gets a streak of a certain length
	UPROPERTY(EditDefaultsOnly)
	TMap<int32, FGameplayTag> ElimStreakTags;

	// Runtime behavior and state are intentionally absent from this benchmark starter.
};
